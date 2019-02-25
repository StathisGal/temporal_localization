import os
import numpy as np
import glob

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable

from action_net import ACT_net
from tcn import TCN

from create_tubes_from_boxes import create_tube
from connect_tubes import connect_tubes

class Model(nn.Module):
    """ 
    action localizatio network which contains:
    -ACT_net : a network for proposing action tubes for 16 frames
    -TCN net : a dilation network which classifies the input tubes
    """
    def __init__(self, actions):
        super(Model, self).__init__()

        self.classes = actions
        self.n_classes = len(actions)

        self.act_net = ACT_net(actions)

        ## general options
        self.sample_duration = 16
        # self.step = int(self.sample_duration/2)
        self.step = 8

        ### tcn options
        ## TODO optimize them

        input_channels = 512
        nhid = 25 ## number of hidden units per levels
        levels = 8
        channel_sizes = [nhid] * levels
        kernel_size = 7
        dropout = 0.05

        self.tcn_net = TCN(input_channels, self.n_classes, channel_sizes, kernel_size = kernel_size, dropout=dropout)

    def forward(self, input_video, im_info, gt_tubes, gt_rois,  num_boxes):

        # print('input_video.shape :',input_video.shape)
        # print('im_info :',im_info)
        # print('gt_tubes :',gt_tubes)
        # print('num_boxes :',num_boxes)
        
        # JUST for now only 1 picture support
        n_frames = im_info[0, 2].long() # video shape : (bs, 3, n_fr, 112, 112,)

        if n_frames < 17:
            indexes = [0]
        else:
            indexes = range(0, (n_frames.data -self.sample_duration  ), self.step)

        tubes = []
        pooled_feats = []
        feats = torch.zeros((len(indexes),128, 512, 16)).type_as(input_video)

        for i in indexes:

            lim = min(i+self.sample_duration-1, (n_frames-1))
            vid_indices = torch.arange(i,lim-1).long()

            vid_seg = input_video[:,:,vid_indices]
            gt_rois_seg = gt_rois[:,:,vid_indices]
            ## TODO remove that and just filter gt_tubes
            gt_tubes_seg = create_tube(gt_rois_seg, im_info, 16)
            # print('gt_tubes_seg.shape :',gt_tubes_seg.shape)
            # print('gt_tubes_seg :',gt_tubes_seg)
            # print('gt_tubes :',gt_tubes)
            ## run ACT_net
            rois,  bbox_pred, rois_feat, \
            rpn_loss_cls,  rpn_loss_bbox, \
            act_loss_cls,  act_loss_bbox, rois_label = self.act_net(vid_seg,
                                                                    im_info,
                                                                    gt_tubes_seg,
                                                                    gt_rois_seg,
                                                                    num_boxes)

            tubes, pooled_feats = connect_tubes(tubes,rois, pooled_feats, rois_feat,  i)

        ###################################
        #           Time for TCN          #
        ###################################

        cls_prob = torch.zeros((len(tubes),self.n_classes)).type_as(input_video)
        cls_loss = torch.zeros(len(tubes)).type_as(input_video)
        for i in range(len(tubes)):
            
            tubes_t = torch.Tensor(tubes[i]).type_as(input_video)
            feat = torch.zeros(len(tubes[i]),512,16).type_as(input_video)
            feat = Variable(feat)
            target = Variable(tubes_t[0,7].expand(16).long())
            for j in range(len(pooled_feats[i])):
                feat[j] = pooled_feats[i][j]
            feat = feat.permute(1,0,2).mean(2).unsqueeze(0)
            tmp_prob = self.tcn_net(feat)
            cls_prob[i] = F.softmax(tmp_prob,0)
            # loss = F.nll_loss(output, tubes_t[0,7].unsqueeze(0).long())
            # if self.training:
            # print('cls_prob[i].shape :', cls_prob[i].shape, ' tubes_t[0,7].shape', tubes_t[0,7].unsqueeze(0).shape, ' tubes_t[0,7] ',  tubes_t[0,7])
        # print('cls_loss.shape :',cls_loss.shape)
        # print('cls_prob.shape :',cls_prob.shape)
        # print('tubes_t[0,7].unsqueeze(0).expand(16,-1).shape :',tubes_t[0,7].expand(16).shape)
        cls_loss = F.cross_entropy(cls_prob, target)
        # print('cls_loss.shape :',cls_loss)
        if self.training:
            return rois, bbox_pred,  cls_prob, rpn_loss_cls, rpn_loss_bbox, act_loss_bbox, cls_loss

        return tubes, bbox_pred,  cls_prob, 

    def create_architecture(self):

        self.act_net.create_architecture()
