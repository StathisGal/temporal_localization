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
        nhid = 25
        levels = 8
        channel_sizes = [nhid] * levels
        kernel_size = 7
        dropout = 0.05

        self.tcn_net = TCN(input_channels, self.n_classes, channel_sizes, kernel_size = kernel_size, dropout=dropout)

    def forward(self, input_video, im_info, gt_tubes, gt_rois,  num_boxes):

        print('input_video.shape :',input_video.shape)
        print('im_info :',im_info)
        print('num_boxes :',num_boxes)

        batch_size = input_video.size(0)
        print('batch_size :',batch_size)
        # for b in range(batch_size):
        #     n_frames = im_info[b, 2].long() # video shape : (bs, 3, n_fr, 112, 112,)
        n_frames = im_info[:, 2].long() # video shape : (bs, 3, n_fr, 112, 112,)
        # for i in range(0, (n_frames.data -self.sample_duration  ), self.step):
        indexes = range(0, (n_frames.data -self.sample_duration  ), self.step)

        tubes = []
        pooled_feats = []
        feats = torch.zeros((len(indexes),128, 512, 16)).type_as(input_video)
        print('feats.shape :',feats.shape)
        for i in [0,1]:
        # for i in indexes:
            
            vid_indices = torch.range(i,i+self.sample_duration-1).long()
            vid_seg = input_video[:,:,vid_indices]
            gt_rois_seg = gt_rois[:,:,i:i+self.sample_duration]

            ## TODO remove that and just filter gt_tubes
            gt_tubes_seg = create_tube(gt_rois_seg, im_info, 16)
            print('gt_tubes_seg.shape :',gt_tubes_seg.shape)
            ## run ACT_net
            rois,  bbox_pred, rois_feat, \
            rpn_loss_cls,  rpn_loss_bbox, \
            act_loss_cls,  act_loss_bbox, rois_label = self.act_net(vid_seg,
                                                                    im_info,
                                                                    gt_tubes_seg,
                                                                    gt_rois_seg,
                                                                    num_boxes)
            # tubes = connect_tubes(tubes,torch.round(rois), i)
            tubes, pooled_feats = connect_tubes(tubes,rois, pooled_feats, rois_feat,  i)

        ##########################################################

        # if self.training:
        #     n_tubes = len(tubes)

        # else:

        
        return 0
    
    def create_architecture(self):

        self.act_net.create_architecture()
