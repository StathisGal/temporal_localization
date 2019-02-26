import os
import numpy as np

import torch
import torch.nn as nn
from torch.autograd import Variable
from torch.utils.data import DataLoader

from resnet_3D import resnet34
from jhmdb_dataset import Video

from net_utils import adjust_learning_rate
from spatial_transforms import (
    Compose, Normalize, Scale, CenterCrop, ToTensor, Resize)
from temporal_transforms import LoopPadding
from model import Model
from resize_rpn import resize_rpn, resize_tube
import pdb

np.random.seed(42)

def bbox_overlaps_batch_3d(tubes, gt_tubes):
    """
    tubes: (N, 6) ndarray of float
    gt_tubes: (b, K, 5) ndarray of float

    overlaps: (N, K) ndarray of overlap between boxes and query_boxes
    """
    batch_size = gt_tubes.size(0)

    if tubes.dim() == 2:

        N = tubes.size(0)
        K = gt_tubes.size(1)

        tubes = tubes[:,1:]
        tubes = tubes.view(1, N, 6)
        tubes = tubes.expand(batch_size, N, 6).contiguous()
        gt_tubes = gt_tubes[:, :, :6].contiguous()

        gt_tubes_x = (gt_tubes[:, :, 3] - gt_tubes[:, :, 0] + 1)
        gt_tubes_y = (gt_tubes[:, :, 4] - gt_tubes[:, :, 1] + 1)
        gt_tubes_t = (gt_tubes[:, :, 5] - gt_tubes[:, :, 2] + 1)

        if batch_size == 1:  # only 1 video in batch:
            gt_tubes_x = gt_tubes_x.unsqueeze(0)
            gt_tubes_y = gt_tubes_y.unsqueeze(0)
            gt_tubes_t = gt_tubes_t.unsqueeze(0)

        gt_tubes_area = (gt_tubes_x * gt_tubes_y * gt_tubes_t)
        gt_tubes_area_xy = gt_tubes_x * gt_tubes_y

        tubes_boxes_x = (tubes[:, :, 3] - tubes[:, :, 0] + 1)
        tubes_boxes_y = (tubes[:, :, 4] - tubes[:, :, 1] + 1)
        tubes_boxes_t = (tubes[:, :, 5] - tubes[:, :, 2] + 1)

        tubes_area = (tubes_boxes_x * tubes_boxes_y *
                        tubes_boxes_t).view(batch_size, N, 1)  # for 1 frame
        tubes_area_xy = (tubes_boxes_x * tubes_boxes_y).view(batch_size, N, 1)  # for 1 frame
        
        gt_area_zero = (gt_tubes_x == 1) & (gt_tubes_y == 1) & (gt_tubes_t == 1)
        tubes_area_zero = (tubes_boxes_x == 1) & (tubes_boxes_y == 1) & (tubes_boxes_t == 1)

        gt_area_zero_xy = (gt_tubes_x == 1) & (gt_tubes_y == 1) 
        tubes_area_zero_xy = (tubes_boxes_x == 1) & (tubes_boxes_y == 1) 

        gt_area_zero_t =  (gt_tubes_t == 1)
        tubes_area_zero_t =  (tubes_boxes_t == 1)

        boxes = tubes.view(batch_size, N, 1, 6)
        boxes = boxes.expand(batch_size, N, K, 6)
        query_boxes = gt_tubes.view(batch_size, 1, K, 6)
        query_boxes = query_boxes.expand(batch_size, N, K, 6)

        iw = (torch.min(boxes[:, :, :, 3], query_boxes[:, :, :, 3]) -
              torch.max(boxes[:, :, :, 0], query_boxes[:, :, :, 0]) + 1)

        iw[iw < 0] = 0

        ih = (torch.min(boxes[:, :, :, 4], query_boxes[:, :, :, 4]) -
              torch.max(boxes[:, :, :, 1], query_boxes[:, :, :, 1]) + 1)
        ih[ih < 0] = 0

        it = (torch.min(boxes[:, :, :, 5], query_boxes[:, :, :, 5]) -
              torch.max(boxes[:, :, :, 2], query_boxes[:, :, :, 2]) + 1)
        it[it < 0] = 0

        ua = tubes_area + gt_tubes_area - (iw * ih * it)
        ua_xy = tubes_area_xy + gt_tubes_area_xy - (iw * ih )
        ua_t = tubes_boxes_t.unsqueeze(2) + gt_tubes_t - it

        # print('ua.shape :',ua.shape)
        # print('ua_xy.shape :',ua_xy.shape)
        # print('tubes_boxes_t.shape :',tubes_boxes_t.shape)
        # print('gt_tubes_t.shape :',gt_tubes_t.shape)
        # print('it :',it.shape)
        # print('ua_t :',ua_t.shape)
        # print('tubes_area.shape :',tubes_area.shape)
        # print('tubes_boxes_t.shape :',tubes_boxes_t.unsqueeze(2)
        #       .shape)
        # print('gt_tubes_area.shape :',gt_tubes_area.shape)
        # print('gt_tubes_t.shape :', gt_tubes_t.shape)
        overlaps = iw * ih * it / ua
        overlaps_xy = iw * ih  / ua_xy
        overlaps_t = it / ua_t

        overlaps.masked_fill_(gt_area_zero.view(
            batch_size, 1, K).expand(batch_size, N, K), 0)
        overlaps.masked_fill_(tubes_area_zero.view(
            batch_size, N, 1).expand(batch_size, N, K), -1)

        overlaps_xy.masked_fill_(gt_area_zero.view(
            batch_size, 1, K).expand(batch_size, N, K), 0)
        overlaps_xy.masked_fill_(tubes_area_zero.view(
            batch_size, N, 1).expand(batch_size, N, K), -1)

        overlaps_t.masked_fill_(gt_area_zero.view(
            batch_size, 1, K).expand(batch_size, N, K), 0)
        overlaps_t.masked_fill_(tubes_area_zero.view(
            batch_size, N, 1).expand(batch_size, N, K), -1)

    else:
        raise ValueError('tubes input dimension is not correct.')

    return overlaps, overlaps_xy, overlaps_t

def validation(epoch, device, model, dataset_folder, sample_duration, spatial_transform, temporal_transform, boxes_file, splt_txt_path, cls2idx, batch_size, n_threads):

    iou_thresh = 0.5 # Intersection Over Union thresh
    data = Video(dataset_folder, frames_dur=sample_duration, spatial_transform=spatial_transform,
                 temporal_transform=temporal_transform, json_file = boxes_file,
                 split_txt_path=splt_txt_path, mode='val', classes_idx=cls2idx)
    data_loader = torch.utils.data.DataLoader(data, batch_size=batch_size,
                                              shuffle=False, num_workers=n_threads, pin_memory=True)
    model.eval()
    true_pos = torch.zeros(1).long().to(device)
    false_neg = torch.zeros(1).long().to(device)

    true_pos_xy = torch.zeros(1).long().to(device)
    false_neg_xy = torch.zeros(1).long().to(device)

    true_pos_t = torch.zeros(1).long().to(device)
    false_neg_t = torch.zeros(1).long().to(device)

    correct_preds = torch.zeros(1).long().to(device)
    n_preds = torch.zeros(1).long().to(device)
    preds = torch.zeros(1).long().to(device)
    ## 2 rois : 1450
    tubes_sum = 0
    for step, data  in enumerate(data_loader):

        # if step == 2:
        #     break
        # print('step :',step)

        clips,  (h, w), gt_tubes_r, gt_rois, n_actions, frames, target = data
        
        clips = clips.to(device)
        gt_tubes_r = gt_tubes_r.to(device)
        # print('gt_tubes_r :',gt_tubes_r)
        # print('frames :',frames)
        n_actions = n_actions.to(device)
        target = target.to(device)
        im_info = torch.Tensor([[sample_size, sample_size, sample_duration]] ).to(device)
        inputs = Variable(clips)
        tubes,  bbox_pred, cls_prob   = model(inputs,
                                             im_info,
                                             None, gt_rois,
                                             n_actions)

        # print('gt_bues_r.shape :',gt_tubes_r.shape)
        # print('cls_prob.shape :',cls_prob.shape)
        # print('len(tubes) :',len(tubes))
        n_tubes = len(tubes)

        _, cls_int = torch.max(cls_prob,1)
        # print('cls_int :',cls_int, ' target :', target)
        for k in cls_int.cpu().tolist():
            if k == target.data:
                print('Found one')
                correct_preds += 1
            n_preds += 1
        for i in range(gt_tubes_r.size(0)): # how many frames we have
            tubes_t = torch.zeros(n_tubes, 7).type_as(gt_tubes_r)
            for j in range(n_tubes):
                # print('J :',j, 'i :',i)
                # print(' len(tube[j]) :',len(tubes[j]))
                # print('tubes[j] :',tubes[j])
                # print('tubes[j][i] :',tubes[j][i])
                
                if (len(tubes[j]) - 1 < i):
                    continue
                tubes_t[j] = torch.Tensor(tubes[j][i][:7]).type_as(tubes_t)
            
            overlaps, overlaps_xy, overlaps_t = bbox_overlaps_batch_3d(tubes_t.squeeze(0), gt_tubes_r[i].unsqueeze(0)) # check one video each time

            ## for the whole tube
            gt_max_overlaps, _ = torch.max(overlaps, 1)
            gt_max_overlaps = torch.where(gt_max_overlaps > iou_thresh, gt_max_overlaps, torch.zeros_like(gt_max_overlaps).type_as(gt_max_overlaps))
            detected =  gt_max_overlaps.ne(0).sum()
            n_elements = gt_max_overlaps.nelement()
            true_pos += detected
            false_neg += n_elements - detected

            ## for xy - area
            gt_max_overlaps_xy, _ = torch.max(overlaps_xy, 1)
            gt_max_overlaps_xy = torch.where(gt_max_overlaps_xy > iou_thresh, gt_max_overlaps_xy, torch.zeros_like(gt_max_overlaps_xy).type_as(gt_max_overlaps_xy))

            detected_xy =  gt_max_overlaps_xy.ne(0).sum()
            n_elements_xy = gt_max_overlaps_xy.nelement()
            true_pos_xy += detected_xy
            false_neg_xy += n_elements_xy - detected_xy

            ## for t - area
            gt_max_overlaps_t, _ = torch.max(overlaps_t, 1)
            gt_max_overlaps_t = torch.where(gt_max_overlaps_t > iou_thresh, gt_max_overlaps_t, torch.zeros_like(gt_max_overlaps_t).type_as(gt_max_overlaps_t))
            detected_t =  gt_max_overlaps_t.ne(0).sum()
            n_elements_t = gt_max_overlaps_t.nelement()
            true_pos_t += detected_t
            false_neg_t += n_elements_t - detected_t

            tubes_sum += 1


    recall    = true_pos.float()    / (true_pos.float()    + false_neg.float())
    recall_xy = true_pos_xy.float() / (true_pos_xy.float() + false_neg_xy.float())
    recall_t  = true_pos_t.float()  / (true_pos_t.float()  + false_neg_t.float())
    print('recall :',recall)
    print(' -----------------------')
    print('| Validation Epoch: {: >3} | '.format(epoch+1))
    print('|                       |')
    print('| Proposed Action Tubes |')
    print('|                       |')
    print('| In {: >6} steps    :  |\n| True_pos   --> {: >6} |\n| False_neg  --> {: >6} | \n| Recall     --> {: >6.4f} |'.format(
        step, true_pos.cpu().tolist()[0], false_neg.cpu().tolist()[0], recall.cpu().tolist()[0]))
    print('|                       |')
    print('| In xy area            |')
    print('|                       |')
    print('| In {: >6} steps    :  |\n| True_pos   --> {: >6} |\n| False_neg  --> {: >6} | \n| Recall     --> {: >6.4f} |'.format(
        step, true_pos_xy.cpu().tolist()[0], false_neg_xy.cpu().tolist()[0], recall_xy.cpu().tolist()[0]))
    print('|                       |')
    print('| In time area          |')
    print('|                       |')
    print('| In {: >6} steps    :  |\n| True_pos   --> {: >6} |\n| False_neg  --> {: >6} | \n| Recall     --> {: >6.4f} |'.format(
        step, true_pos_t.cpu().tolist()[0], false_neg_t.cpu().tolist()[0], recall_t.cpu().tolist()[0]))
    print('|                       |')
    print('| Classification        |')
    print('|                       |')
    print('| In {: >6} steps    :  |'.format(step))
    print('|                       |')
    print('| Correct preds :       |\n| {: >6} / {: >6}       |'.format( correct_preds.cpu().tolist()[0], n_preds.cpu().tolist()[0]))


    print(' -----------------------')
        
if __name__ == '__main__':

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print("Device being used:", device)

    dataset_folder = '/gpu-data/sgal/JHMDB-act-detector-frames'
    split_txt_path =  '/gpu-data/sgal/splits'
    boxes_file = '../temporal_localization/poses.json'

    sample_size = 112
    sample_duration = 16  # len(images)

    batch_size = 1
    # batch_size = 1
    n_threads = 0

    # # get mean
    # mean =  [103.75581543 104.79421473  91.16894564] # jhmdb
    mean = [103.29825354, 104.63845484,  90.79830328]  # jhmdb from .png
    # mean = [112.07945832, 112.87372333, 106.90993363]  # ucf-101 24 classes
    # generate model

    classes = ['__background__', 'brush_hair', 'clap', 'golf', 'kick_ball', 'pour',
               'push', 'shoot_ball', 'shoot_gun', 'stand', 'throw', 'wave',
               'catch','climb_stairs', 'jump', 'pick', 'pullup', 'run', 'shoot_bow', 'sit',
               'swing_baseball', 'walk' ]


    cls2idx = {classes[i]: i for i in range(0, len(classes))}

    spatial_transform = Compose([Scale(sample_size),  # [Resize(sample_size),
                                 ToTensor(),
                                 Normalize(mean, [1, 1, 1])])
    temporal_transform = LoopPadding(sample_duration)

    # Init action_net
    model = Model(classes)
    model.create_architecture()
    model_data = torch.load('./jmdb_model.pwf')

    model.load_state_dict(model_data)

    model = nn.DataParallel(model)
    model.to(device)

    model.eval()

    validation(0, device, model, dataset_folder, sample_duration, spatial_transform, temporal_transform, boxes_file, split_txt_path, cls2idx, batch_size, n_threads)