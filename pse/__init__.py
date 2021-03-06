import subprocess
import os
import numpy as np
import cv2
import torch
from util.config import config as cfg
from scipy import ndimage as ndimg
from util import canvas as cav
BASE_DIR = os.path.dirname(os.path.realpath(__file__))

if subprocess.call(['make', '-C', BASE_DIR]) != 0:  # return value
    raise RuntimeError('Cannot compile pse: {}'.format(BASE_DIR))


def sigmoid_alpha(x, k):
    betak = (1 + np.exp(-k)) / (1 - np.exp(-k))
    dm = max(np.max(x), 0.0001)
    res = (2 / (1 + np.exp(-x*k/dm)) - 1)*betak
    return np.maximum(0, res)

def pse_warpper(kernals, min_area=5):
    '''
    reference https://github.com/liuheng92/tensorflow_PSENet/blob/feature_dev/pse
    :param kernals:
    :param min_area:
    :return:
    '''
    from .pse import pse_cpp
    kernal_num = len(kernals)
    if not kernal_num:
        return np.array([]), []
    kernals = np.array(kernals)
    label_num, label = cv2.connectedComponents(kernals[0].astype(np.uint8), connectivity=4)
    label_values = []
    for label_idx in range(1, label_num):
        if np.sum(label == label_idx) < min_area:
            label[label == label_idx] = 0
            continue
        label_values.append(label_idx)

    pred = pse_cpp(label, kernals, c=kernal_num)

    return np.array(pred), label_values


def decode(preds, scale, threshold=0.33):
    """
    在输出上使用sigmoid 将值转换为置信度，并使用阈值来进行文字和背景的区分
    :param preds: 网络输出
    :param scale: 网络的scale
    :param threshold: sigmoid的阈值
    :return: 最后的输出图和文本框
    """
    preds = torch.sigmoid(preds)
    preds = preds.detach().cpu().numpy()
    score = preds[-1].astype(np.float32)
    # score = preds[1:].astype(np.float32)
    preds = preds > threshold
    # preds = preds * preds[-1] # 使用最大的kernel作为其他小图的mask,不使用的话效果更好
    pred, label_values = pse_warpper(preds, cfg.min_area)
    bbox_list = []
    polygons = []
    for label_value in label_values:
        mask = pred == label_value
        if np.sum(mask) < 300 / (scale * scale):  # 150 / 300
            continue
        score_i = np.mean(score[pred == label_value])
        if score_i < cfg.score_i:
            continue

        # binary-二值化结果，contours-轮廓信息，hierarchy-层级
        contours, hierarchy = cv2.findContours(mask.astype(np.uint8), cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

        rect = cv2.minAreaRect(contours[0])
        points = cv2.boxPoints(rect)
        points = np.int0(points)

        # 轮廓近似，epsilon数值越小，越近似
        epsilon = 0.007 * cv2.arcLength(contours[0], True)
        approx = cv2.approxPolyDP(contours[0], epsilon, True)
        polygons.append(approx.reshape((-1, 2)))

        bbox_list.append(points)

    return pred, bbox_list, polygons
