import os
import numpy as np

import torch
import torch.nn as nn
from torch.autograd import Variable
from torch.utils.data import DataLoader

from video_dataset import Video_UCF, video_names

from spatial_transforms import (
    Compose, Normalize, Scale, CenterCrop, ToTensor, Resize)
from temporal_transforms import LoopPadding

from create_video_id import get_vid_dict
from net_utils import adjust_learning_rate
from resize_rpn import resize_rpn, resize_tube

from model import Model
from action_net import ACT_net

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

        tubes_boxes_x = (tubes[:, :, 3] - tubes[:, :, 0] + 1)
        tubes_boxes_y = (tubes[:, :, 4] - tubes[:, :, 1] + 1)
        tubes_boxes_t = (tubes[:, :, 5] - tubes[:, :, 2] + 1)

        tubes_area = (tubes_boxes_x * tubes_boxes_y *
                        tubes_boxes_t).view(batch_size, N, 1)  # for 1 frame
        gt_area_zero = (gt_tubes_x == 1) & (gt_tubes_y == 1) 
        tubes_area_zero = (tubes_boxes_x == 1) & (tubes_boxes_y == 1)

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
        overlaps = iw * ih * it / ua
        overlaps.masked_fill_(gt_area_zero.view(
            batch_size, 1, K).expand(batch_size, N, K), 0)
        overlaps.masked_fill_(tubes_area_zero.view(
            batch_size, N, 1).expand(batch_size, N, K), -1)
    else:
        raise ValueError('tubes input dimension is not correct.')

    return overlaps

def validation(epoch, device, model, dataset_folder, sample_duration, spatial_transform, temporal_transform, boxes_file, splt_txt_path, cls2idx, batch_size, n_threads):

    iou_thresh = 0.5 # Intersection Over Union thresh
    data = Video(dataset_folder, frames_dur=sample_duration, spatial_transform=spatial_transform,
                 temporal_transform=temporal_transform, json_file = boxes_file,
                 split_txt_path=splt_txt_path, mode='val', classes_idx=cls2idx)
    data_loader = torch.utils.data.DataLoader(data, batch_size=batch_size,
                                              shuffle=True, num_workers=n_threads, pin_memory=True)
    model.eval()
    true_pos = torch.zeros(1).long().to(device)
    false_neg = torch.zeros(1).long().to(device)
    ## 2 rois : 1450
    for step, data  in enumerate(data_loader):

        if step == 2:
            break

        clips,  (h, w), gt_tubes_r, gt_rois, n_actions, n_frames = data
        clips = clips.to(device)
        gt_tubes_r = gt_tubes_r.to(device)
        n_actions = n_actions.to(device)
        im_info = torch.Tensor([[sample_size, sample_size, n_frames]] * gt_tubes_r.size(1)).to(device)
        inputs = Variable(clips)
        tubes,  bbox_pred, cls_prob   = model(inputs,
                                             im_info,
                                             gt_tubes_r, gt_rois,
                                             n_actions)

        overlaps = bbox_overlaps_batch_3d(tubes.squeeze(0), gt_tubes_r) # check one video each time
        gt_max_overlaps, _ = torch.max(overlaps, 1)
        gt_max_overlaps = torch.where(gt_max_overlaps > iou_thresh, gt_max_overlaps, torch.zeros_like(gt_max_overlaps).type_as(gt_max_overlaps))
        detected =  gt_max_overlaps.ne(0).sum()
        n_elements = gt_max_overlaps.nelement()
        true_pos += detected
        false_neg += n_elements - detected

    recall = true_pos.float() / (true_pos.float() + false_neg.float())
    print('recall :',recall)
    print(' -----------------------')
    print('| Validation Epoch: {: >3} | '.format(epoch+1))
    print('|                       |')
    print('| Proposed Action Tubes |')
    print('|                       |')
    print('| In {: >6} steps    :  |\n| True_pos   --> {: >6} |\n| False_neg  --> {: >6} | \n| Recall     --> {: >6.4f} |'.format(
        step, true_pos.cpu().tolist()[0], false_neg.cpu().tolist()[0], recall.cpu().tolist()[0]))
    print(' -----------------------')
        
def training(epoch, device, model, dataset_folder, sample_duration, spatial_transform, temporal_transform, boxes_file, splt_txt_path, cls2idx, batch_size, n_threads, lr,):

    data = Video_UCF(dataset_folder, frames_dur=sample_duration, spatial_transform=spatial_transform,
                 temporal_transform=temporal_transform, json_file = boxes_file,
                 split_txt_path=splt_txt_path, mode='train', classes_idx=cls2idx)
    data_loader = torch.utils.data.DataLoader(data, batch_size=batch_size,
                                              shuffle=True, num_workers=n_threads, pin_memory=True)
    n_classes = len(classes)
    resnet_shortcut = 'A'

    model.train()
    loss_temp = 0
    
    ## 2 rois : 1450
    for step, data  in enumerate(data_loader):

        if step == 2:
            break

        clips,  (h, w), gt_tubes_r, gt_rois, n_actions, n_frames = data
        clips = clips.to(device)
        gt_tubes_r = gt_tubes_r.to(device)
        gt_rois = gt_rois.to(device)
        # print('gt_tubes_r :',gt_tubes_r)
        # print('gt_tubes :',gt_tubes)
        # h = h.to(device)
        # w = w.to(device)
        # gt_tubes = gt_tubes.to(device)
        n_actions = n_actions.to(device)
        im_info = torch.Tensor([[sample_size, sample_size, n_frames]] * gt_tubes_r.size(1)).to(device)
        # print('gt_rois.shape :',gt_rois.shape )
        inputs = Variable(clips)
        rois,  bbox_pred, cls_prob, \
        rpn_loss_cls, rpn_loss_bbox, \
        act_loss_cls, act_loss_bbox  = model(inputs,
                                             im_info,
                                             gt_tubes_r, gt_rois,
                                             n_actions)
        # print('rois :',rois)
        # print('rpn_loss_bbox :',rpn_loss_bbox)
        # print('rpn_loss_cls :',rpn_loss_cls)
        loss = rpn_loss_cls.mean() + rpn_loss_bbox.mean() + act_loss_bbox.mean() + act_loss_cls.mean()
        # loss = rpn_loss_cls.mean() + rpn_loss_bbox.mean() + act_loss_bbox.mean() 
        loss_temp += loss.item()

        # backw\ard
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

    print('Train Epoch: {} \tLoss: {:.6f}\t lr : {:.6f}'.format(
        epoch+1,loss_temp/step, lr))

    return model, loss_temp

if __name__ == '__main__':

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print("Device being used:", device)

    dataset_folder = '/gpu-data2/sgal/UCF-101-frames'
    boxes_file = '/gpu-data2/sgal/pyannot.pkl'
    spt_path = '/gpu-data2/sgal/UCF101_Action_detection_splits/'

    sample_size = 112
    sample_duration = 16  # len(images)

    # # get mean
    mean = [112.07945832, 112.87372333, 106.90993363]  # ucf-101 24 classes


    # generate model
    actions = ['__background__', 'Basketball','BasketballDunk','Biking','CliffDiving','CricketBowling',
               'Diving','Fencing','FloorGymnastics','GolfSwing','HorseRiding','IceDancing',
               'LongJump','PoleVault','RopeClimbing','SalsaSpin','SkateBoarding','Skiing',
               'Skijet','SoccerJuggling','Surfing','TennisSwing','TrampolineJumping',
               'VolleyballSpiking','WalkingWithDog']


    cls2idx = {actions[i]: i for i in range(0, len(actions))}

    ### get videos id
    vid2idx,vid_names = get_vid_dict(dataset_folder)

    spatial_transform = Compose([Scale(sample_size),  # [Resize(sample_size),
                                 ToTensor(),
                                 Normalize(mean, [1, 1, 1])])
    temporal_transform = LoopPadding(sample_duration)

    n_classes = len(actions)


    # ########################################
    # #          Part 1 - train TPN          #
    # ########################################

    # ##########################################
    # #          Model Initialization          #
    # ##########################################

    # # Init action_net
    # act_model = ACT_net(actions, sample_duration)
    # act_model.create_architecture()
    # if torch.cuda.device_count() > 1:
    #     print('Using {} GPUs!'.format(torch.cuda.device_count()))

    #     act_model = nn.DataParallel(act_model)

    # act_model.to(device)

    # lr = 0.1
    # lr_decay_step = 10
    # lr_decay_gamma = 0.1
    

    # params = []
    # for key, value in dict(act_model.named_parameters()).items():
    #     # print(key, value.requires_grad)
    #     if value.requires_grad:
    #         print('key :',key)
    #         if 'bias' in key:
    #             params += [{'params':[value],'lr':lr*(True + 1), \
    #                         'weight_decay': False and 0.0005 or 0}]
    #         else:
    #             params += [{'params':[value],'lr':lr, 'weight_decay': 0.0005}]

    # lr = lr * 0.1
    # optimizer = torch.optim.Adam(params)

    # # epochs = 40
    # epochs = 40
    # for epoch in range(epochs):
    #     print(' ============\n| Epoch {:0>2}/{:0>2} |\n ============'.format(epoch+1, epochs))

    #     if epoch % (lr_decay_step + 1) == 0:
    #         adjust_learning_rate(optimizer, lr_decay_gamma)
    #         lr *= lr_decay_gamma


    #         act_model, loss = training(epoch, device, act_model, dataset_folder, sample_duration, spatial_transform, temporal_transform, boxes_file, split_txt_path, cls2idx, batch_size, n_threads, lr)

    #     # if (epoch + 1) % (5) == 0:
    #     #     validation(epoch, device, model, dataset_folder, sample_duration, spatial_transform, temporal_transform, boxes_file, split_txt_path, cls2idx, batch_size, n_threads)


    # #     if ( epoch + 1 ) % 5 == 0:
    # #         torch.save(model.state_dict(), "action_net_model.pwf".format(epoch+1))
    # # torch.save(model.state_dict(), "action_net_model.pwf".format(epoch))

    # ###########################################
    # #          Part 2 - train Linear          #
    # ###########################################
    
    # first initialize model

    model = Model(actions, sample_duration, sample_size)
    model.create_architecture()

    if torch.cuda.device_count() > 1:

        print('Using {} GPUs!'.format(torch.cuda.device_count()))
        model.act_net = nn.DataParallel(model.act_net)

    model.act_net = model.act_net.cuda()

    # init data_loaders
    
    vid_name_loader = video_names(dataset_folder, spt_path, boxes_file, vid2idx, mode='train')
    data_loader = torch.utils.data.DataLoader(vid_name_loader, batch_size=1,
                                              shuffle=True)
    # reset learning rate
    lr = 0.1
    lr_decay_step = 5
    lr_decay_gamma = 0.1

    params = []
    for key, value in dict(model.linear.named_parameters()).items():
        # print(key, value.requires_grad)
        if value.requires_grad:
            print('key :',key)
            if 'bias' in key:
                params += [{'params':[value],'lr':lr*(True + 1), \
                            'weight_decay': False and 0.0005 or 0}]
            else:
                params += [{'params':[value],'lr':lr, 'weight_decay': 0.0005}]

    lr = lr * 0.1
    optimizer = torch.optim.Adam(params)

    ##########################
    
    epochs = 40 
    for epoch in range(epochs):
        print(' ============\n| Epoch {:0>2}/{:0>2} |\n ============'.format(epoch+1, epochs))

        if epoch % (lr_decay_step + 1) == 0:
            adjust_learning_rate(optimizer, lr_decay_gamma)
            lr *= lr_decay_gamma

        for step, data  in enumerate(data_loader):

            # if step == 2:
            #     break
            print('step :',step)
            vid_id, boxes, n_frames, n_actions, h, w = data


