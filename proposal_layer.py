from __future__ import absolute_import
# --------------------------------------------------------
# Faster R-CNN
# Copyright (c) 2015 Microsoft
# Licensed under The MIT License [see LICENSE for details]
# Written by Ross Girshick and Sean Bell
# --------------------------------------------------------
# --------------------------------------------------------
# Reorganized and modified by Jianwei Yang and Jiasen Lu
# --------------------------------------------------------

import torch
import torch.nn as nn
import numpy as np
import math
import yaml
# from config import cfg
from conf import conf
from generate_anchors import generate_anchors_all_pyramids
# from generate_anchors import generate_anchors
# from bbox_transform import bbox_transform_inv, clip_boxes_3d, clip_boxes_batch, bbox_transform_inv_3d
from box_functions import bbox_transform_inv,clip_boxes
from nms_3d.nms_wrapper import nms
import pdb

DEBUG = False

class _ProposalLayer(nn.Module):
    """
    Outputs object detection proposals by applying estimated bounding-box
    transformations to a set of regular boxes (called "anchors").
    """

    def __init__(self, feat_stride, scales, ratios, time_dim,num_anchors):
        super(_ProposalLayer, self).__init__()

        self.sample_duration = time_dim[0]
        self.time_dim = time_dim
        self._fpn_scales = scales
        self._anchor_ratios = ratios
        self._fpn_feature_strides = np.array([ 4, 8, 16, 32])
        self._fpn_anchor_stride  = 1

    def forward(self, input):

        # Algorithm:
        #
        # for each (H, W) location i
        #   generate A anchor boxes centered on cell i
        #   apply predicted bbox deltas at cell i to each of the A anchors
        # clip predicted boxes to image
        # remove predicted boxes with either height or width < threshold
        # sort all (proposal, score) pairs by score from highest to lowest
        # take top pre_nms_topN proposals before NMS
        # apply NMS with threshold 0.7 to remaining proposals
        # take after_nms_topN proposals after NMS
        # return the top proposals (-> RoIs top, scores top)


        # the first set of _num_anchors channels are bg probs
        # the second set are the fg probs

        scores = input[0][ :, :, :, 1]
        scores_3_4 = input[1][ :, :, :, 1]
        scores_2 = input[2][ :, :, :, 1]
        bbox_frame = input[3]
        bbox_frame_3_4 = input[4]
        bbox_frame_2 = input[5]
        im_info = input[6]
        cfg_key = input[7]
        feat_shapes = input[8]
        
        # print('bbox_frame.shape :',bbox_frame.shape)
        # print('bbox_frame.shape :',bbox_frame_3_4.shape)
        # print('bbox_frame.shape :',bbox_frame_2.shape)
        # print('scores.shape :',scores.shape)
        # print('scores_3_4.shape :',scores_3_4.shape)
        # print('scores_2.shape :',scores_2.shape)
        # print('feat_shapes :',feat_shapes)
        batch_size = bbox_frame.size(0)

        pre_nms_topN  = conf[cfg_key].RPN_PRE_NMS_TOP_N
        post_nms_topN = conf[cfg_key].RPN_POST_NMS_TOP_N
        nms_thresh    = conf[cfg_key].RPN_NMS_THRESH
        min_size      = conf[cfg_key].RPN_MIN_SIZE

        ##################
        # Create anchors #
        ##################

        anchors = torch.from_numpy(generate_anchors_all_pyramids(self._fpn_scales, self._anchor_ratios, 
                feat_shapes, self._fpn_feature_strides, self._fpn_anchor_stride)).type_as(scores)
        
        num_anchors = anchors.size(0)

        # # get time anchors
        anchors_all = []
        bbox_frame_all = []
                
        bboxes = [bbox_frame, bbox_frame_3_4, bbox_frame_2]


        for i in range(len(self.time_dim)):
            for j in range(0,self.sample_duration-self.time_dim[i]+1):
                anc = torch.zeros((self.sample_duration,anchors.size(0),4))
                bbox =  torch.zeros((batch_size, anchors.size(0),self.sample_duration,4))
                
                anc[ j:j+self.time_dim[i]] = anchors
                anc = anc.permute(1,0,2)
                t = bboxes[i][:,j].view(batch_size, anchors.size(0), self.time_dim[i],4)

                bbox[:,:,j:j+self.time_dim[i],:] = t

                anchors_all.append(anc)
                bbox_frame_all.append(bbox)

        anchors_all = torch.cat(anchors_all,0).type_as(scores)
        bbox_frame_all = torch.cat(bbox_frame_all,0).type_as(scores)

        anchors_all = anchors_all.view(1,anchors_all.size(0), self.sample_duration * 4).\
                      expand(batch_size, anchors_all.size(0), self.sample_duration * 4)
        bbox_frame_all = bbox_frame_all.view(batch_size, -1, self.sample_duration * 4)

        # # Same story for the scores:

        scores = scores.view(batch_size, -1)
        scores_3_4 = scores_3_4.view(batch_size, -1)
        scores_2 = scores_2.view(batch_size, -1)

        scores_all = torch.cat([scores, scores_3_4, scores_2],1)

        # Convert anchors into proposals via bbox transformations
        proposals = bbox_transform_inv(anchors_all.contiguous().view(-1,anchors_all.size(2)),\
                                       bbox_frame_all.contiguous().view(-1,anchors_all.size(2)), \
                                       (1.0, 1.0, 1.0, 1.0)) # proposals have 441 * time_dim shape

        # 2. clip predicted boxes to image
        ## if any dimension exceeds the dims of the original image, clamp_ them
        proposals = proposals.view(batch_size,-1,self.sample_duration*4)
        proposals = clip_boxes(proposals, im_info, batch_size)

        scores_keep = scores
        proposals_keep = proposals

        _, order = torch.sort(scores, 1, True)
        
        output = scores.new(batch_size, post_nms_topN, self.sample_duration*4+2).zero_()
        # print('output.shape :',output.shape)
        for i in range(batch_size):
            # # 3. remove predicted boxes with either height or width < threshold
            # # (NOTE: convert min_size to input image scale stored in im_info[2])
            proposals_single = proposals_keep[i]
            scores_single = scores_keep[i]
            order_single = order[i]

            if pre_nms_topN > 0 and pre_nms_topN < scores_keep.numel() and cfg_key == 'TEST':
                order_single = order_single[:pre_nms_topN]

            proposals_single = proposals_single[order_single, :]
            scores_single = scores_single[order_single].view(-1,1)

            if cfg_key =='TEST' :

                keep_idx_i = nms(torch.cat((proposals_single, scores_single), 1), nms_thresh)
                keep_idx_i = keep_idx_i.long().view(-1)

                if post_nms_topN > 0:
                    keep_idx_i = keep_idx_i[:post_nms_topN]
                    proposals_single = proposals_single[keep_idx_i, :]
                    scores_single = scores_single[keep_idx_i, :]
            
                    # adding score at the end.
                    num_proposal = proposals_single.size(0)
                    output[i,:num_proposal,0] = i
                    output[i,:num_proposal,1:-1] = proposals_single
                    output[i,:num_proposal,-1] = scores_single.squeeze()

            else:
                ## without NMS code
                proposals_single = proposals_single[:post_nms_topN, :]
                scores_single = scores_single[:post_nms_topN]
            
                # adding score at the end.
                num_proposal = proposals_single.size(0)
                output[i,:num_proposal,0] = i
                output[i,:num_proposal,1:-1] = proposals_single
                output[i,:num_proposal,-1] = scores_single.squeeze()

        return output

    def backward(self, top, propagate_down, bottom):
        """This layer does not propagate gradients."""
        pass

    def reshape(self, bottom, top):
        """Reshaping happens during the call to forward."""
        pass

    def _filter_boxes(self, boxes, min_size):
        """Remove all boxes with any side smaller than min_size."""
        ws = boxes[:, :, 2] - boxes[:, :, 0] + 1
        hs = boxes[:, :, 3] - boxes[:, :, 1] + 1
        keep = ((ws >= min_size.view(-1,1).expand_as(ws)) & (hs >= min_size.view(-1,1).expand_as(hs)))
        return keep
