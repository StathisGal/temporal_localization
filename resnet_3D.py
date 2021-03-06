import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
import math
from functools import partial
# from faster3d import _fasterRCNN3D

__all__ = ['ResNet', 'resnet10', 'resnet18', 'resnet34', 'resnet50', 'resnet101', 'resnet152', 'resnet200']


def conv3x3x3(in_planes, out_planes, stride=1):
    # 3x3x3 convolution with padding
    return nn.Conv3d(in_planes, out_planes, kernel_size=3,
                     stride=stride, padding=1, bias=False)


def downsample_basic_block(x, planes, stride):
    out = F.avg_pool3d(x, kernel_size=1, stride=stride)
    zero_pads = torch.Tensor(out.size(0), planes - out.size(1),
                             out.size(2), out.size(3),
                             out.size(4)).zero_()
    if isinstance(out.data, torch.cuda.FloatTensor):
        zero_pads = zero_pads.cuda()

    out = Variable(torch.cat([out.data, zero_pads], dim=1))

    return out


class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, inplanes, planes, stride=1, downsample=None):
        super(BasicBlock, self).__init__()
        self.conv1 = conv3x3x3(inplanes, planes, stride)
        self.bn1 = nn.BatchNorm3d(planes)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = conv3x3x3(planes, planes)
        self.bn2 = nn.BatchNorm3d(planes)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)

        return out


class Bottleneck(nn.Module):
    expansion = 4

    def __init__(self, inplanes, planes, stride=1, downsample=None):
        super(Bottleneck, self).__init__()
        self.conv1 = nn.Conv3d(inplanes, planes, kernel_size=1, bias=False)
        self.bn1 = nn.BatchNorm3d(planes)
        self.conv2 = nn.Conv3d(planes, planes, kernel_size=3, stride=stride,
                               padding=1, bias=False)
        self.bn2 = nn.BatchNorm3d(planes)
        self.conv3 = nn.Conv3d(planes, planes * 4, kernel_size=1, bias=False)
        self.bn3 = nn.BatchNorm3d(planes * 4)
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)
        out = self.relu(out)

        out = self.conv3(out)
        out = self.bn3(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)

        return out


class ResNet(nn.Module):

    def __init__(self, block, layers, sample_size, sample_duration, shortcut_type='B', num_classes=400, last_fc=True):
        self.last_fc = last_fc

        self.inplanes = 64
        super(ResNet, self).__init__()
        self.conv1 = nn.Conv3d(3, 64, kernel_size=7, stride=(1, 2, 2),
                               padding=(3, 3, 3), bias=False)
        self.bn1 = nn.BatchNorm3d(64)
        self.relu = nn.ReLU(inplace=True)
        # stride from (2,2,2) goes to (1,2,2) in order to maintain all 16 pictures
        self.maxpool = nn.MaxPool3d(kernel_size=(3, 3, 3), stride=(1,2,2), padding=1) 
        # self.maxpool = nn.MaxPool3d(kernel_size=(3, 3, 3), stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0], shortcut_type)
        self.layer2 = self._make_layer(block, 128, layers[1], shortcut_type, stride=(1,2,2)) #
        self.layer3 = self._make_layer(block, 256, layers[2], shortcut_type, stride=(1,2,2))
        self.layer4 = self._make_layer(block, 512, layers[3], shortcut_type, stride=(1,2,2))
        last_duration = math.ceil(sample_duration / 16)
        last_size = math.ceil(sample_size / 32)
        self.avgpool = nn.AvgPool3d((last_duration, last_size, last_size), stride=1)
        self.fc = nn.Linear(512 * block.expansion, num_classes)

        for m in self.modules():
            if isinstance(m, nn.Conv3d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
            elif isinstance(m, nn.BatchNorm3d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def _make_layer(self, block, planes, blocks, shortcut_type, stride=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            if shortcut_type == 'A':
                downsample = partial(downsample_basic_block,
                                     planes=planes * block.expansion,
                                     stride=stride)
            else:
                downsample = nn.Sequential(
                    nn.Conv3d(self.inplanes, planes * block.expansion,
                              kernel_size=1, stride=stride, bias=False),
                    nn.BatchNorm3d(planes * block.expansion)
                )

        layers = []
        layers.append(block(self.inplanes, planes, stride, downsample))
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            layers.append(block(self.inplanes, planes))

        return nn.Sequential(*layers)

    def forward(self, x):
        # print('first we have: ', x.shape)
        x = self.conv1(x)
        # print('after conv1: ', x.shape)
        x = self.bn1(x)
        # print('after bn1: ', x.shape)
        x = self.relu(x)
        # print('after relu: ', x.shape)
        x = self.maxpool(x)
        # print('after 1st maxpool shape: ', x.shape)
        x = self.layer1(x)
        # print('after layer1 :', x.shape)
        x = self.layer2(x)
        # print('after layer2 :', x.shape)
        x = self.layer3(x)
        # print('after layer3 :', x.shape)
        # x = self.layer4(x)
        # print('after layer4 :', x.shape)
        

        # x = self.avgpool(x)

        # x = x.view(x.size(0), -1)

        # if self.last_fc:
        #     x = self.fc(x)

        return x

class ResNet_multi(nn.Module):

    def __init__(self, block, layers, sample_size, sample_duration, shortcut_type='B', num_classes=400, last_fc=True):
        self.last_fc = last_fc

        self.inplanes = 64
        super(ResNet_multi, self).__init__()
        self.conv1 = nn.Conv3d(3, 64, kernel_size=7, stride=(1, 2, 2),
                               padding=(3, 3, 3), bias=False)
        self.bn1 = nn.BatchNorm3d(64)
        self.relu = nn.ReLU(inplace=True)
        # stride from (2,2,2) goes to (1,2,2) in order to maintain all 16 pictures
        self.maxpool = nn.MaxPool3d(kernel_size=(3, 3, 3), stride=(1,2,2), padding=1) 
        # self.maxpool = nn.MaxPool3d(kernel_size=(3, 3, 3), stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0], shortcut_type)
        self.layer2 = self._make_layer(block, 128, layers[1], shortcut_type, stride=(1,2,2)) #
        self.layer3 = self._make_layer(block, 256, layers[2], shortcut_type, stride=(1,2,2))
        self.layer4 = self._make_layer(block, 512, layers[3], shortcut_type, stride=(1,2,2))
        last_duration = math.ceil(sample_duration / 16)
        last_size = math.ceil(sample_size / 32)
        self.avgpool = nn.AvgPool3d((last_duration, last_size, last_size), stride=1)
        self.fc = nn.Linear(512 * block.expansion, num_classes)

        for m in self.modules():
            if isinstance(m, nn.Conv3d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
            elif isinstance(m, nn.BatchNorm3d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def _make_layer(self, block, planes, blocks, shortcut_type, stride=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            if shortcut_type == 'A':
                downsample = partial(downsample_basic_block,
                                     planes=planes * block.expansion,
                                     stride=stride)
            else:
                downsample = nn.Sequential(
                    nn.Conv3d(self.inplanes, planes * block.expansion,
                              kernel_size=1, stride=stride, bias=False),
                    nn.BatchNorm3d(planes * block.expansion)
                )

        layers = []
        layers.append(block(self.inplanes, planes, stride, downsample))
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            layers.append(block(self.inplanes, planes))

        return nn.Sequential(*layers)

    def forward(self, x):
        print('first we have: ', x.shape)
        x = self.conv1(x)
        print('after conv1: ', x.shape)
        x = self.bn1(x)
        print('after bn1: ', x.shape)
        x = self.relu(x)
        print('after relu: ', x.shape)
        x = self.maxpool(x)
        print('after 1st maxpool shape: ', x.shape)
        layer1 = self.layer1(x)
        print('after layer1 :', x.shape)
        layer2 = self.layer2(layer1)
        print('after layer2 :', x.shape)
        layer3 = self.layer3(layer2)
        print('after layer3 :', x.shape)
        layer4 = self.layer4(layer3)

        return layer4,layer3, layer2, layer1

class ResNet_framechange(nn.Module):

    def __init__(self, block, layers, sample_size, sample_duration, shortcut_type='B', num_classes=400, last_fc=True):
        self.last_fc = last_fc

        self.inplanes = 64
        super(ResNet_framechange, self).__init__()
        self.conv1 = nn.Conv3d(3, 64, kernel_size=7, stride=(1, 2, 2),
                               padding=(3, 3, 3), bias=False)
        self.bn1 = nn.BatchNorm3d(64)
        self.relu = nn.ReLU(inplace=True)
        # stride from (2,2,2) goes to (1,2,2) in order to maintain all 16 pictures
        self.maxpool = nn.MaxPool3d(kernel_size=(3, 3, 3), stride=2, padding=1) 
        # self.maxpool = nn.MaxPool3d(kernel_size=(3, 3, 3), stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0], shortcut_type)
        self.layer2 = self._make_layer(block, 128, layers[1], shortcut_type, stride=2) #
        self.layer3 = self._make_layer(block, 256, layers[2], shortcut_type, stride=2)
        self.layer4 = self._make_layer(block, 512, layers[3], shortcut_type, stride=2)
        last_duration = math.ceil(sample_duration / 16)
        last_size = math.ceil(sample_size / 32)
        self.avgpool = nn.AvgPool3d((last_duration, last_size, last_size), stride=1)
        self.fc = nn.Linear(512 * block.expansion, num_classes)

        for m in self.modules():
            if isinstance(m, nn.Conv3d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
            elif isinstance(m, nn.BatchNorm3d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def _make_layer(self, block, planes, blocks, shortcut_type, stride=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            if shortcut_type == 'A':
                downsample = partial(downsample_basic_block,
                                     planes=planes * block.expansion,
                                     stride=stride)
            else:
                downsample = nn.Sequential(
                    nn.Conv3d(self.inplanes, planes * block.expansion,
                              kernel_size=1, stride=stride, bias=False),
                    nn.BatchNorm3d(planes * block.expansion)
                )

        layers = []
        layers.append(block(self.inplanes, planes, stride, downsample))
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            layers.append(block(self.inplanes, planes))

        return nn.Sequential(*layers)

    def forward(self, x):
        print('first we have: ', x.shape)
        x = self.conv1(x)
        print('after conv1: ', x.shape)
        x = self.bn1(x)
        print('after bn1: ', x.shape)
        x = self.relu(x)
        print('after relu: ', x.shape)
        x = self.maxpool(x)
        print('after 1st maxpool shape: ', x.shape)
        layer1 = self.layer1(x)
        print('after layer1 :', x.shape)
        layer2 = self.layer2(layer1)
        print('after layer2 :', x.shape)
        layer3 = self.layer3(layer2)
        print('after layer3 :', x.shape)
        layer4 = self.layer4(layer3)
        layer4 = layer4.squeeze()

        # x = self.avgpool(x)

        # x = x.view(x.size(0), -1)

        # if self.last_fc:
        #     x = self.fc(x)

        return layer4,layer3, layer2, layer1


def get_fine_tuning_parameters(model, ft_begin_index):
    if ft_begin_index == 0:
        return model.parameters()

    ft_module_names = []
    for i in range(ft_begin_index, 5):
        ft_module_names.append('layer{}'.format(ft_begin_index))
    ft_module_names.append('fc')

    parameters = []
    for k, v in model.named_parameters():
        for ft_module in ft_module_names:
            if ft_module in k:
                parameters.append({'params': v})
                break
        else:
            parameters.append({'params': v, 'lr': 0.0})

    return parameters


def resnet10(**kwargs):
    """Constructs a ResNet-18 model.
    """
    model = ResNet(BasicBlock, [1, 1, 1, 1], **kwargs)
    return model

def resnet18(**kwargs):
    """Constructs a ResNet-18 model.
    """
    model = ResNet(BasicBlock, [2, 2, 2, 2], **kwargs)
    return model

def resnet34(**kwargs):
    """Constructs a ResNet-34 model.
    """
    model = ResNet(BasicBlock, [3, 4, 6, 3], **kwargs)
    return model

def resnet34_multi(**kwargs):
    """Constructs a ResNet-34 model.
    """
    model = ResNet(BasicBlock, [3, 4, 6, 3], **kwargs)
    return model

def resnet34_framechange(**kwargs):
    """Constructs a ResNet-34 model.
    """
    model = ResNet_framechange(BasicBlock, [3, 4, 6, 3], **kwargs)
    return model

def resnet50(**kwargs):
    """Constructs a ResNet-50 model.
    """
    model = ResNet(Bottleneck, [3, 4, 6, 3], **kwargs)
    return model

def resnet101(**kwargs):
    """Constructs a ResNet-101 model.
    """
    model = ResNet(Bottleneck, [3, 4, 23, 3], **kwargs)
    return model

def resnet152(**kwargs):
    """Constructs a ResNet-101 model.
    """
    model = ResNet(Bottleneck, [3, 8, 36, 3], **kwargs)
    return model

def resnet200(**kwargs):
    """Constructs a ResNet-101 model.
    """
    model = ResNet(Bottleneck, [3, 24, 36, 3], **kwargs)
    return model


# class resnet(_fasterRCNN3D):
#   def __init__(self,  classes, num_layers=34, pretrained=False, class_agnostic=False, **kwargs):
#     self.model_path = './resnet34_caffe.pth'
#     self.dout_base_model = 1024
#     self.pretrained = pretrained
#     self.class_agnostic = class_agnostic

#     _fasterRCNN3D.__init__(self, classes, class_agnostic)

#   def _init_modules(self, cfg, **kwargs):
#     resnet = resnet34(**kwargs)

#     if self.pretrained == True:
#       print("Loading pretrained weights from %s" %(self.model_path))
#       state_dict = torch.load(self.model_path)
#       resnet.load_state_dict({k:v for k,v in state_dict.items() if k in resnet.state_dict()})

#     # Build resnet.
#     self.RCNN_base = nn.Sequential(resnet.conv1, resnet.bn1,resnet.relu,
#       resnet.maxpool,resnet.layer1,resnet.layer2,resnet.layer3)

#     self.RCNN_top = nn.Sequential(resnet.layer4)

#     self.RCNN_cls_score = nn.Linear(2048, self.n_classes)
#     if self.class_agnostic:
#       self.RCNN_bbox_pred = nn.Linear(2048, 4)
#     else:
#       self.RCNN_bbox_pred = nn.Linear(2048, 4 * self.n_classes)

#     # Fix blocks
#     for p in self.RCNN_base[0].parameters(): p.requires_grad=False
#     for p in self.RCNN_base[1].parameters(): p.requires_grad=False

#     assert (0 <= cfg.RESNET.FIXED_BLOCKS < 4)
#     if cfg.RESNET.FIXED_BLOCKS >= 3:
#       for p in self.RCNN_base[6].parameters(): p.requires_grad=False
#     if cfg.RESNET.FIXED_BLOCKS >= 2:
#       for p in self.RCNN_base[5].parameters(): p.requires_grad=False
#     if cfg.RESNET.FIXED_BLOCKS >= 1:
#       for p in self.RCNN_base[4].parameters(): p.requires_grad=False

#     def set_bn_fix(m):
#       classname = m.__class__.__name__
#       if classname.find('BatchNorm') != -1:
#         for p in m.parameters(): p.requires_grad=False

#     self.RCNN_base.apply(set_bn_fix) # run set_bn_fix function in RCNN_base
#     self.RCNN_top.apply(set_bn_fix)

#   def train(self, mode=True):
#     # Override train so that the training mode is set as we want
#     nn.Module.train(self, mode)
#     if mode:
#       # Set fixed blocks to be in eval mode
#       self.RCNN_base.eval()
#       self.RCNN_base[5].train()
#       self.RCNN_base[6].train()

#       def set_bn_eval(m):
#         classname = m.__class__.__name__
#         if classname.find('BatchNorm') != -1:
#           m.eval()

#       self.RCNN_base.apply(set_bn_eval)
#       self.RCNN_top.apply(set_bn_eval)

#   def _head_to_tail(self, pool5):
#     fc7 = self.RCNN_top(pool5).mean(3).mean(2)
#     return fc7
