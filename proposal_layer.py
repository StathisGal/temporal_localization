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
from config import cfg
from generate_3d_anchors import generate_anchors
from bbox_transform import bbox_transform_inv, clip_boxes, clip_boxes_batch, bbox_frames_transform_inv
from nms.nms_wrapper import nms

import pdb

DEBUG = False

class _ProposalLayer(nn.Module):
    """
    Outputs object detection proposals by applying estimated bounding-box
    transformations to a set of regular boxes (called "anchors").
    """

    def __init__(self, feat_stride, scales, ratios, time_dim):
        super(_ProposalLayer, self).__init__()

        self._feat_stride = feat_stride
        self._anchors = torch.from_numpy(generate_anchors(scales=np.array(scales), 
                                                          ratios=np.array(ratios),
                                                          time_dim=np.array(time_dim)).float()
        self._num_anchors = self._anchors.size(0)

        # rois blob: holds R regions of interest, each is a 5-tuple
        # (n, x1, y1, x2, y2) specifying an image batch index n and a
        # rectangle (x1, y1, x2, y2)
        # top[0].reshape(1, 5)
        #
        # # scores blob: holds scores for R regions of interest
        # if len(top) > 1:
        #     top[1].reshape(1, 1, 1, 1)

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

        scores = input[0][:, self._num_anchors:, :, :]
        bbox_frame = input[1]
        im_info = input[2]
        cfg_key = input[3]
        time_dim = input[4]
        # print('bbox_frame.shape :',bbox_frame.shape)

        batch_size = bbox_frame.size(0)
        # pre_nms_topN  = cfg[cfg_key].RPN_PRE_NMS_TOP_N
        # post_nms_topN = cfg[cfg_key].RPN_POST_NMS_TOP_N
        # nms_thresh    = cfg[cfg_key].RPN_NMS_THRESH
        # min_size      = cfg[cfg_key].RPN_MIN_SIZE
        if cfg_key == 'TRAIN':
            pre_nms_topN  = 12000
            post_nms_topN = 2000
            nms_thresh    = 0.7
            min_size      = 8
        else:
            pre_nms_topN  = 6000
            post_nms_topN = 300
            nms_thresh    = 0.7
            min_size      = 16

        ##################
        # Create anchors #
        ##################

        # print('batch_size :', batch_size)
        feat_height, feat_width = scores.size(2), scores.size(3)
        shift_x = np.arange(0, feat_width) * self._feat_stride
        shift_y = np.arange(0, feat_height) * self._feat_stride
        shift_x, shift_y = np.meshgrid(shift_x, shift_y)
        shifts = torch.from_numpy(np.vstack((shift_x.ravel(), shift_y.ravel(),
                                  shift_x.ravel(), shift_y.ravel())).transpose())
        shifts = shifts.contiguous().type_as(scores).float()

        A = self._num_anchors
        K = shifts.size(0)

        self._anchors = self._anchors.type_as(scores)

        anchors = self._anchors.view(1, A, 4) + shifts.view(K, 1, 4)
        anchors = anchors.view(1, K * A, 4)
        # anchors = anchors.expand(batch_size, K * A, 4)

        frame_anchors = anchors.expand(1,time_dim,K*A,4).contiguous()
        frame_anchors = anchors.expand(batch_size,time_dim,K*A,4).contiguous()
        frame_anchors = frame_anchors.view(batch_size,-1,4) ## same anchors for #time_dim frames
        # print('frame_anchors.shape :',frame_anchors.shape)


        # Transpose and reshape predicted bbox transformations to get them
        # into the same order as the anchors:
        # print('bbox_deltas.shape :', bbox_deltas.shape)

        # bbox_deltas = bbox_deltas.permute(0, 2, 3, 1).contiguous()
        # bbox_deltas = bbox_deltas.view(batch_size, -1, 4)

        # Now for bbox_frame
        # print('bbox_frame.shape :',bbox_frame.shape )

        bbox_frame = bbox_frame.permute(0,2,3,1).contiguous()
        bbox_frame = bbox_frame.view(batch_size,-1,4)

        # Same story for the scores:
        scores = scores.permute(0, 2, 3, 1).contiguous()
        scores = scores.view(batch_size, -1)

        ###############################
        # Until now, everything is ok #
        ###############################
        """
        we have for 16 frames, 7056 anchors,
        first 441 correspond to 441 anchors for the first frame,
        second 441 to the 441 for the sencond frame etc.
        """
        # Convert anchors into proposals via bbox transformations
        # proposals = bbox_frames_transform_inv(anchors, bbox_deltas, batch_size)
        proposals = bbox_frames_transform_inv(frame_anchors, bbox_frame, batch_size) # proposals have 441 * time_dim shape
        # print('proposals.shape :',proposals.shape)
        # print('proposals :',proposals)

        # 2. clip predicted boxes to image
        ## if any dimension exceeds the dims of the original image, clamp_ them
        proposals = clip_boxes(proposals, torch.Tensor(im_info.tolist() * 1).cuda(), 1)

        # print('proposals.shape :',proposals.shape)
        # print('proposals :',proposals)

        # assign the score to 0 if it's non keep.
        # keep = self._filter_boxes(proposals, min_size * im_info[:, 2])

        # trim keep index to make it euqal over batch
        # keep_idx = torch.cat(tuple(keep_idx), 0)

        # scores_keep = scores.view(-1)[keep_idx].view(batch_size, trim_size)
        # proposals_keep = proposals.view(-1, 4)[keep_idx, :].contiguous().view(batch_size, trim_size, 4)
        
        # _, order = torch.sort(scores_keep, 1, True)
        # print('proposals.shape :',proposals.shape)
        proposals_reshaped = proposals.view(batch_size,time_dim, K*A,4)
        proposals_reshaped = proposals_reshaped.permute(0,2,1,3).contiguous()
        proposals_reshaped = proposals_reshaped.view(batch_size,K*A,time_dim*4)
        proposals_reshaped = proposals_reshaped.view(-1,time_dim*4)
        # print('reshaped_proposals.shape :',proposals_reshaped.shape)        

        scores_single = scores.view(-1)
        # print('scores_single.shape :',scores_single.shape)
        _, order_single = torch.sort(scores_single, 0, True)

        
        output = scores.new(post_nms_topN, 4*time_dim + 1).zero_()

        # # 3. remove predicted boxes with either height or width < threshold
        # # (NOTE: convert min_size to input image scale stored in im_info[2])
        # # 4. sort all (proposal, score) pairs by score from highest to lowest
        # # 5. take top pre_nms_topN (e.g. 6000)

        if pre_nms_topN > 0 and pre_nms_topN < scores_single.numel():
            order_single = order_single[:pre_nms_topN]

        proposals_reshaped = proposals_reshaped[order_single, :]
        scores_single = scores_single[order_single].view(-1,1)

        # 6. apply nms (e.g. threshold = 0.7)
        # 7. take after_nms_topN (e.g. 300)
        # 8. return the top proposals (-> RoIs top)

        keep_idx_i = nms(torch.cat((proposals_reshaped, scores_single), 1), nms_thresh, force_cpu=not cfg.USE_GPU_NMS)
        # keep_idx_i = nms(torch.cat((proposals_reshaped, scores_single), 1), nms_thresh, force_cpu=True)
        keep_idx_i = keep_idx_i.long().view(-1)

        if post_nms_topN > 0:
            keep_idx_i = keep_idx_i[:post_nms_topN]
        proposals_reshaped = proposals_reshaped[keep_idx_i, :]
        scores_single = scores_single[keep_idx_i, :]
        # print('scores_single.shape :',scores_single.shape)
        # # padding 0 at the end.
        # print(' scores_single[:,0].shape :', scores_single[:,0].shape)
        # print('output[:,0].shape :',output[:,0].shape)
        num_proposal = proposals_reshaped.size(0)
        output[:num_proposal,0] = scores_single[:,0]
        output[:num_proposal,1:] = proposals_reshaped


        # print('output.shape :',output.shape)
        # print('output :',output)
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
