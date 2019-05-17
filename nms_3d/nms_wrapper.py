# --------------------------------------------------------
# Fast R-CNN
# Copyright (c) 2015 Microsoft
# Licensed under The MIT License [see LICENSE for details]
# Written by Ross Girshick
# --------------------------------------------------------
import torch
# from model.utils.config import cfg
# if torch.cuda.is_available():
#     from nms_gpu import nms_gpu
# from nms_cpu import nms_cpu
if torch.cuda.is_available():
    from .nms_gpu import nms_gpu
from .nms_cpu import nms_cpu


def nms(dets, thresh, force_cpu=False):
    """Dispatch to either CPU or GPU NMS implementations."""
    if dets.shape[0] == 0:
        return []
    # ---numpy version---
    # original: return gpu_nms(dets, thresh, device_id=cfg.GPU_ID)
    # ---pytorch version---

    return nms_gpu(dets, thresh) if force_cpu == False else nms_cpu(dets, thresh)
if __name__ == '__main__':

    t = torch.Tensor([[0.0058, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0034, 0.0015,
                 0.0000, 0.0000, 0.0241, 0.0047, 0.0000, 0.0024, 0.0000, 0.0027, 0.0000,
                 0.0116, 0.0000, 0.0000, 0.0000, 0.0030, 0.0092, 0.0037, 0.0000, 0.0017,
                 0.0105, 0.0033, 0.0000, 0.0000, 0.0078, 0.0011, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0002, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5083],
                [0.0070, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0030, 0.0005,
                 0.0000, 0.0000, 0.0224, 0.0041, 0.0000, 0.0039, 0.0000, 0.0018, 0.0000,
                 0.0166, 0.0000, 0.0000, 0.0000, 0.0039, 0.0102, 0.0021, 0.0000, 0.0000,
                 0.0116, 0.0034, 0.0000, 0.0000, 0.0084, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5082],
                [0.0055, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0056, 0.0000,
                 0.0000, 0.0027, 0.0221, 0.0004, 0.0000, 0.0055, 0.0000, 0.0021, 0.0000,
                 0.0147, 0.0000, 0.0000, 0.0001, 0.0000, 0.0030, 0.0034, 0.0000, 0.0013,
                 0.0103, 0.0021, 0.0011, 0.0000, 0.0001, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5078],

                [1.0055, 2.0000, 3.0000, 4.0000, 1.0055, 2.0000, 3.0000, 4.0000, 1.0055,
                 2.0000, 3.0000, 4.0000, 1.0055, 2.0000, 3.0000, 4.0000, 1.0055, 2.0000,
                 3.0000, 4.0000, 1.0055, 2.0000, 3.0000, 4.0000, 1.0055, 2.0000, 3.0000,
                 4.0000, 1.0055, 2.0000, 3.0000, 4.0000, 1.0055, 2.0000, 3.0000, 4.0000,
                 1.0055, 2.0000, 3.0000, 4.0000, 1.0055, 2.0000, 3.0000, 4.0000, 1.0055,
                 2.0000, 3.0000, 4.0000, 1.0055, 2.0000, 3.0000, 4.0000, 1.0055, 2.0000,
                 3.0000, 4.0000, 1.0055, 2.0000, 3.0000, 4.0000, 1.0055, 2.0000, 3.0000,
                 4.0000,0.5078],

                [0.0000, 0.0000, 0.0000, 0.0125, 0.0000, 0.0000, 0.0148, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0024, 0.0000, 0.0009, 0.0000, 0.0140, 0.0051, 0.0016,
                 0.0028, 0.0037, 0.0000, 0.0000, 0.0000, 0.0000, 0.0019, 0.0000, 0.0055,
                 0.0000, 0.0051, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5072],
                [0.0057, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0077, 0.0000,
                 0.0004, 0.0037, 0.0201, 0.0002, 0.0001, 0.0051, 0.0000, 0.0009, 0.0000,
                 0.0165, 0.0000, 0.0000, 0.0000, 0.0000, 0.0034, 0.0028, 0.0000, 0.0000,
                 0.0122, 0.0021, 0.0015, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5071],
                [0.0000, 0.0000, 0.0000, 0.0142, 0.0000, 0.0000, 0.0118, 0.0004, 0.0000,
                 0.0000, 0.0005, 0.0021, 0.0000, 0.0032, 0.0003, 0.0178, 0.0035, 0.0034,
                 0.0014, 0.0055, 0.0000, 0.0000, 0.0000, 0.0000, 0.0027, 0.0019, 0.0017,
                 0.0000, 0.0051, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5070],
                [0.0065, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0045, 0.0000,
                 0.0000, 0.0000, 0.0199, 0.0036, 0.0000, 0.0050, 0.0000, 0.0012, 0.0000,
                 0.0152, 0.0000, 0.0000, 0.0004, 0.0070, 0.0121, 0.0028, 0.0000, 0.0007,
                 0.0141, 0.0038, 0.0000, 0.0000, 0.0112, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5069],
                [0.0043, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0044, 0.0003,
                 0.0000, 0.0000, 0.0222, 0.0043, 0.0000, 0.0027, 0.0000, 0.0025, 0.0003,
                 0.0124, 0.0000, 0.0000, 0.0000, 0.0076, 0.0112, 0.0027, 0.0000, 0.0025,
                 0.0125, 0.0032, 0.0000, 0.0000, 0.0118, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5068],
                [0.0000, 0.0024, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0020, 0.0000,
                 0.0000, 0.0028, 0.0143, 0.0000, 0.0000, 0.0280, 0.0017, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0027, 0.0056, 0.0000, 0.0043, 0.0171,
                 0.0000, 0.0099, 0.0064, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5066],
                [0.0000, 0.0000, 0.0000, 0.0175, 0.0000, 0.0000, 0.0118, 0.0000, 0.0000,
                 0.0000, 0.0033, 0.0000, 0.0000, 0.0012, 0.0000, 0.0146, 0.0039, 0.0014,
                 0.0018, 0.0051, 0.0000, 0.0000, 0.0000, 0.0000, 0.0031, 0.0000, 0.0037,
                 0.0000, 0.0063, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5066],
                [0.0000, 0.0020, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0049, 0.0000,
                 0.0000, 0.0019, 0.0152, 0.0000, 0.0000, 0.0271, 0.0018, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0022, 0.0047, 0.0000, 0.0033, 0.0193,
                 0.0000, 0.0105, 0.0063, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5065],
                [0.0000, 0.0000, 0.0000, 0.0190, 0.0000, 0.0000, 0.0103, 0.0000, 0.0000,
                 0.0000, 0.0019, 0.0000, 0.0000, 0.0029, 0.0000, 0.0189, 0.0036, 0.0020,
                 0.0021, 0.0076, 0.0000, 0.0000, 0.0000, 0.0000, 0.0037, 0.0000, 0.0033,
                 0.0000, 0.0055, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5064],
                [0.0000, 0.0046, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0012, 0.0000,
                 0.0000, 0.0049, 0.0131, 0.0000, 0.0000, 0.0297, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0059, 0.0072, 0.0032, 0.0043, 0.0199,
                 0.0000, 0.0099, 0.0074, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000, 0.0000,
                 0.0000, 0.5062]]).cuda()
    print('t.shape :',t.shape)
    
    ret =nms(t, 0.5, force_cpu=False)
