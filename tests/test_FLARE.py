'''
This is the test code of IBD-PSC defense.
IBD-PSC: Input-level Backdoor Detection via Parameter-oriented Scaling Consistency [ICML, 2024] (https://arxiv.org/abs/2405.09786) 

'''


from copy import deepcopy
import os.path as osp

import numpy as np
import random
import cv2
import os
import torch
import torch.nn as nn
import torch.nn.functional as F

import torchvision
import torchvision.transforms as transforms
from torchvision.datasets import DatasetFolder
from torch.utils.data import Subset
from torchvision.transforms import Compose, RandomHorizontalFlip, ToTensor, ToPILImage, Resize
import sys 
sys.path.append('/home/hou/data/houls/BackdoorBox-main')
import core


# ========== Set global settings ==========
global_seed = 666
# deterministic = True
deterministic = False
torch.manual_seed(global_seed)
# ========== Set global settings ==========
datasets_root_dir = os.path.expanduser('~/data/dataset')
CUDA_VISIBLE_DEVICES = '0'
portion = 0.1
batch_size = 128
num_workers = 4


def test(model_name, dataset_name, attack_name, defense_name, benign_dataset, attacked_dataset, defense, y_target):
    schedule = {
        'device': 'GPU',
        'CUDA_VISIBLE_DEVICES': CUDA_VISIBLE_DEVICES,
        'GPU_num': 1,

        'batch_size': batch_size,
        'num_workers': num_workers,

        'metric': 'BA',

        'save_dir': 'experiments/IBD-PSC-defense',
        'experiment_name': f'{model_name}_{dataset_name}_{attack_name}_{defense_name}_BA'
    }
    defense.test_acc(benign_dataset, schedule)
    if not attack_name == 'Benign':
        schedule = {
            'device': 'GPU',
            'CUDA_VISIBLE_DEVICES': CUDA_VISIBLE_DEVICES,
            'GPU_num': 1,

            'batch_size': batch_size,
            'num_workers': num_workers,

            # 1. ASR: the attack success rate calculated on all poisoned samples
            # 2. ASR_NoTarget: the attack success rate calculated on all poisoned samples whose ground-truth labels are not the target label
            # 3. BA: the accuracy on all benign samples
            # Hint: For ASR and BA, the computation of the metric is decided by the dataset but not schedule['metric'].
            # In other words, ASR or BA does not influence the computation of the metric.
            # For ASR_NoTarget, the code will delete all the samples whose ground-truth labels are the target label and then compute the metric.
            'metric': 'ASR_NoTarget',
            'y_target': y_target,

            'save_dir': 'experiments/IBD-PSC-defense',
            'experiment_name': f'{model_name}_{dataset_name}_{attack_name}_{defense_name}_ASR'
        }
        defense.test_acc(attacked_dataset, schedule)

dataset = torchvision.datasets.CIFAR10
transform_train = Compose([
    RandomHorizontalFlip(),
    ToTensor()
])
trainset = dataset(datasets_root_dir, train=True, transform=transform_train, download=True)
transform_test = Compose([
    ToTensor()
])
testset = dataset(datasets_root_dir, train=False, transform=transform_test, download=True)
# # ========== ResNet-18_CIFAR-10_Attack_Defense FLARE ==========
poisoning_rate = 0.1
target_label = 1
# ===================== BadNets ======================
model_name, dataset_name, attack_name, defense_name = 'ResNet-18', 'CIFAR-10', 'BadNets', 'FLARE'
badnet_model = core.models.ResNet(18, num_classes=10)
model_path = '/home/hou/data/houls/BackdoorBox-main/experiments/ResNet-18_CIFAR-10_BadNets_2025-06-18_22:02:44/ckpt_epoch_200.pth'

def load_dict(model_path):
    state_dict = torch.load(model_path)
    # print(state_dict)
    if 'model' in list(state_dict.keys()):
        return state_dict['model']
    else:
        return state_dict
badnet_model.load_state_dict(load_dict(model_path))


trigger = torch.tensor([
    [0., 0., 1.],
    [0., 1., 0.],
    [1., 0., 1.]
])  # shape: (3, 3)

pattern = torch.zeros((32, 32), dtype=torch.uint8)
weight = torch.zeros((32, 32), dtype=torch.float32)

pattern[-3:, -3:] = (trigger * 255).to(torch.uint8)
weight[-3:, -3:] = 1.0

# Get BadNets poisoned dataset
attack = core.BadNets(
    train_dataset=trainset,
    test_dataset=testset,
    model=core.models.ResNet(18, num_classes=10),
    loss=nn.CrossEntropyLoss(),
    y_target=target_label,
    poisoned_rate=poisoning_rate,
    pattern=pattern,
    weight=weight,
    seed=global_seed,
    deterministic=deterministic
)
poisoned_trainset, poisoned_testset = attack.get_poisoned_dataset()
poison_indices = poisoned_trainset.poisoned_set
# print(poison_indices)
# print(dataset_name.lower())

num_img = len(testset)
indices = list(range(0, num_img))
random.shuffle(indices)
val_budget = 2000
val_indices = indices[:val_budget]
val_set = Subset(testset, val_indices)


train_num = len(trainset)
all_indices = set(range(train_num))
# clean_indices = list(all_indices - set(poison_indices))
y_true = torch.zeros(train_num)
y_true[list(poison_indices)] = 1

defense = core.FLARE(model=badnet_model)
print(f'the BA and ASR of the original BadNets model: ............. ')
test(model_name, dataset_name, attack_name, defense_name, testset, poisoned_testset, defense, None)
defense.detect(poisoned_trainset, y_true)


