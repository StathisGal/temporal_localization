import os
import numpy as np
import glob

from  tqdm import tqdm

import torch
import torch.nn as nn
from torch.autograd import Variable
from torch.utils.data import DataLoader

from resnet_3D import resnet34
from video_dataset import Video
from spatial_transforms import (
    Compose, Normalize, Scale, CenterCrop, ToTensor, Resize)
from temporal_transforms import LoopPadding
from action_net import ACT_net
from resize_rpn import resize_rpn, resize_tube
import pdb

np.random.seed(42)

if __name__ == '__main__':

    # torch.cuda.device_count()
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    print("Device being used:", device)

    dataset_folder = '/gpu-data/sgal/UCF-101-frames'
    boxes_file = './pyannot.pkl'
    # boxes_file = '/gpu-data/sgal/UCF-bboxes.json'
    # dataset_folder = '../UCF-101-frames'
    # boxes_file = '../UCF-101-frames/UCF-bboxes.json'

    sample_size = 112
    sample_duration = 16  # len(images)

    batch_size = 1
    n_threads = 4

    # # get mean
    # mean =  [103.75581543 104.79421473  91.16894564] # jhmdb
    # mean = [103.29825354, 104.63845484,  90.79830328]  # jhmdb from .png
    mean = [112.07945832, 112.87372333, 106.90993363]  # ucf-101 24 classes
    # generate model
    last_fc = False

    # classes = ['basketballdunk', 'basketballshooting','cliffdiving', 'cricketbowling', 'fencing', 'floorgymnastics',
    #            'icedancing', 'longjump', 'polevault', 'ropeclimbing', 'salsaspin', 'skateboarding',
    #            'skiing', 'skijet', 'surfing', 'biking', 'diving', 'golfswing', 'horseriding',
    #            'soccerjuggling', 'tennisswing', 'trampolinejumping', 'volleyballspiking', 'walking']

    actions = ['Basketball','BasketballDunk','Biking','CliffDiving','CricketBowling',
               'Diving','Fencing','FloorGymnastics','GolfSwing','HorseRiding','IceDancing',
               'LongJump','PoleVault','RopeClimbing','SalsaSpin','SkateBoarding','Skiing',
               'Skijet','SoccerJuggling','Surfing','TennisSwing','TrampolineJumping',
               'VolleyballSpiking','WalkingWithDog']

    cls2idx = {actions[i]: i for i in range(0, len(actions))}

    spatial_transform = Compose([Scale(sample_size),  # [Resize(sample_size),
                                 ToTensor(),
                                 Normalize(mean, [1, 1, 1])])
    temporal_transform = LoopPadding(sample_duration)

    data = Video(dataset_folder, frames_dur=sample_duration, spatial_transform=spatial_transform,
                 temporal_transform=temporal_transform, json_file=boxes_file,
                 mode='train', classes_idx=cls2idx)
    data_loader = torch.utils.data.DataLoader(data, batch_size=batch_size,
                                              shuffle=True, num_workers=n_threads, pin_memory=True)

    n_classes = len(actions)
    resnet_shortcut = 'A'

    lr = 0.001

    # Init action_net
    model = ACT_net(actions)

    if torch.cuda.device_count() > 1:
        print('Using {} GPUs!'.format(torch.cuda.device_count()))

        model = nn.DataParallel(model)

    model.to(device)

    clips,  (h, w), gt_tubes, gt_rois = data[0]
    clips = clips.unsqueeze(0)


    
    gt_tubes = gt_tubes.unsqueeze(0)
    gt_rois = gt_rois.unsqueeze(0)
    # print('gt_tubes : ',gt_tubes)
    # print('gt_rois.shape : ',gt_rois.shape)
    gt_tubes = gt_tubes[:,0,:].unsqueeze(1).to(device)
    gt_rois = gt_rois[:,0,:,:].unsqueeze(1).to(device)

    # print('gt_tubes : ',gt_tubes)
    # print('gt_tubes.shape : ',gt_tubes.shape)
    # print('gt_tubes[0,0,5] - gt_tube[0,0,2]+1 :',gt_tubes[0,0,5] - gt_tubes[0,0,2]+1)
    # print('gt_tubes[0,0,5] - gt_tube[0,0,2]+1 != 16 :',gt_tubes[0,0,5] - gt_tubes[0,0,2]+1 != 16)

    # print('gt_tubes :',gt_tubes)
    gt_rois =  gt_rois.squeeze(0)

    # print('gt_tubes.shape :',gt_tubes.shape )
    # print('gt_rois.shape :',gt_rois.shape)

    # gt_tubes_r = resize_tube(gt_tubes, h,w,sample_size)
    # gt_rois_r = resize_rpn(gt_rois, h,w,112)

    # inputs = Variable(clips)
    # print('gt_tubes.shape :',gt_tubes.shape )
    # print('gt_rois.shape :',gt_rois.shape)
    print('gt_rois.shape : ',gt_rois.shape)
    print('gt_rois : ',gt_rois)
    print('gt_tubes.shape :',gt_tubes.shape)
    print('gt_tubes :',gt_tubes)
    print('torch.Tensor([[h, w]] * gt_tubes.size(1)).to(device).shape :',torch.Tensor([[h, w]] * gt_tubes.size(1)).to(device))

    rois,  bbox_pred, rpn_loss_cls, \
    rpn_loss_bbox,  act_loss_bbox, rois_label = model(clips,
                                                      torch.Tensor([[h, w]] * gt_tubes.size(1)).to(device),
                                                      gt_tubes, gt_rois,
                                                      torch.Tensor(len(gt_tubes)).to(device))


