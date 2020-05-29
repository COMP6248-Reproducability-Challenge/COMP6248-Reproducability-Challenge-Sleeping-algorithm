# -*- coding: utf-8 -*-
"""SleepNetwork.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1vn6py2GYeQmka0F5UWh21riJgvD36G6j
"""

import torch
import torchbearer
import torch.nn.functional as F
import torchvision.transforms as transforms
from torch import nn
from torch import optim
from torch.utils.data import DataLoader
from torchvision.datasets import MNIST
import numpy as np
import pickle
from torchbearer.callbacks import LiveLossPlot
from itertools import product
from scipy.ndimage import gaussian_filter
import numpy as np
from matplotlib import pyplot as plt
import random
import torch.nn.functional as F
from torch import nn
import sys

# fix random seed for reproducibility
seed = 7
torch.manual_seed(seed)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
np.random.seed(seed)
device = "cuda:0" if torch.cuda.is_available() else "cpu"

# flatten 28*28 images to a 784 vector for each image
transform = transforms.Compose([
    transforms.ToTensor(),  # convert to tensor
    transforms.Lambda(lambda x: x.view(-1))  # flatten into vector
])

class NetworkControl(nn.Module):
    def __init__(self, input_size, hidden_size, num_classes):
        super(NetworkControl, self).__init__()
        self.fc1 = nn.Linear(input_size, hidden_size) 
        self.fc2 = nn.Linear(hidden_size, hidden_size) 
        self.fc3 = nn.Linear(hidden_size, num_classes)  
    
    def forward(self, x):
        out = self.fc1(x)
        out = F.relu(out)
        out = F.dropout(out, 0.2)        
        out = self.fc2(out)        
        out = F.relu(out)
        out = F.dropout(out, 0.2)        
        out = self.fc3(out)
        if not self.training:
            out = F.softmax(out, dim=1)
        return out

# initalize data for sleeping network 
trainset = MNIST(".", train=True, download=True, transform=transform)
testset = MNIST(".", train=False, download=True, transform=transform)
#split the data
trainset.data = trainset.data[0:27105]
trainset.targets = trainset.targets[0:27105]
# # print(trainset.targets[0:11905])
trainloader = DataLoader(trainset, batch_size=128, shuffle=True)
testloader = DataLoader(testset, batch_size=128, shuffle=True)

model = torch.load('save_ann.pkl')
loss_function = nn.CrossEntropyLoss()
# live_loss_plot = LiveLossPlot()
optimiser = optim.SGD(model.parameters(), lr=0.1, momentum=0.5)
# trial = torchbearer.Trial(model, optimiser, loss_function, callbacks=[live_loss_plot], metrics=['loss', 'accuracy']).to(device)
trial = torchbearer.Trial(model, optimiser, loss_function,metrics=['loss', 'accuracy']).to(device)
trial.with_generators(trainloader, test_generator=testloader)
results = trial.evaluate(data_key=torchbearer.TEST_DATA)
print(results)

def sleep(model, inputs, scales):
    changenum = 0
    #The parameters like alpha,beta,etc,you can change to find better performance
    num_features = inputs.shape[0]
    Ts = inputs.shape[1]
    dt = 0.01
    InputRate = 40
    sleepDur = inputs.shape[1]
    dec = 0.03
    sleep_inc = 0.0065
    sleep_dec = 0.0069 
    sleep_beta = [15.579, 0.35, 16.52]  
#     25.516308 0.344342 13.197703
    previous_factor = 1
    alpha = 0.98 
    updateswitch = 0
    
    norm_constants = torch.zeros(3,1).cuda(device)
    
    #initalize spiking network
    InputLayer_spikes = torch.zeros(784,1).cuda(device)
    InputLayer_mem = torch.zeros(784,1).cuda(device)
    InputLayer_refrac_end = torch.zeros(784,1).cuda(device)
    InputLayer_sum_spikes = torch.zeros(784,1).cuda(device)
    
    fc1_spikes = torch.zeros(1200,1).cuda(device)
    fc1_mem = torch.zeros(1200,1).cuda(device)
    fc1_refrac_end = torch.zeros(1200,1).cuda(device)
    fc1_sum_spikes = torch.zeros(1200,1).cuda(device)
    
    fc2_spikes = torch.zeros(1200,1).cuda(device)
    fc2_mem = torch.zeros(1200,1).cuda(device)
    fc2_refrac_end = torch.zeros(1200,1).cuda(device)
    fc2_sum_spikes = torch.zeros(1200,1).cuda(device)

    fc3_spikes = torch.zeros(10,1).cuda(device)
    fc3_mem = torch.zeros(10,1).cuda(device)
    fc3r_refrac_end = torch.zeros(10,1).cuda(device)
    fc3_sum_spikes = torch.zeros(10,1).cuda(device)
    
    ListSpikes = [InputLayer_spikes, fc1_spikes, fc2_spikes, fc3_spikes]
    ListMem = [InputLayer_mem, fc1_mem, fc2_mem, fc3_mem]
    ListRefrac_end= [InputLayer_refrac_end, fc1_refrac_end, fc2_refrac_end, fc3r_refrac_end]
    ListSum_spikes = [InputLayer_sum_spikes, fc1_sum_spikes, fc2_sum_spikes, fc3_sum_spikes]
    weight = [torch.t(torch.t(model.fc1.weight)), torch.t(torch.t(model.fc2.weight)), torch.t(torch.t(model.fc3.weight))]
#     threshold = [0.03618, 0.02336, 0.03638]  
    
    
    
    #get normalization norm_constants
    for i in range(3):
        weight_max = torch.max(weight[i]);
        if   weight_max<0:
            weight_max = 0
        applied_factor = weight_max / previous_factor
        norm_constants[i] = 1 / applied_factor
        previous_factor = applied_factor
            
    sleep_alpha = norm_constants*alpha
    inp_image = torch.zeros(num_features,1).cuda(device) 
    
    
    for i in range(Ts):
#          Create poisson distributed spikes from the input images
        spike_snapshot = torch.rand(num_features,1) * (1/(dt*InputRate))/2
        for idx in range(num_features):
            if spike_snapshot[idx] <= inputs[idx,i]:
                inp_image[idx] = 1


        ListSpikes[0] = inp_image
        ListSum_spikes[0] = ListSum_spikes[0]  + inp_image

        for i in range(1,4):

#             Get input impulse from incoming spike(lose some parameters)
            impulse = sleep_alpha[i-1] * torch.t(ListSpikes[i-1]) @ torch.t(weight[i-1])
#             Add input to membrane potential

            decMem = dec * ListMem[i]
            decMem =decMem.cuda(device)
            ListMem[i] = decMem + torch.t(impulse)
            if i == 3:
                ListMem[i] = ListMem[i]


            if(i == 1):
                print("the max of first layer", torch.max(ListMem[i]))
            if(i == 2):
                print("the max of second layer", torch.max(ListMem[i]))
            if(i == 3):
                print("the max of third layer", torch.max(ListMem[i]))

#           Check for spiking     
            for j in range (ListMem[i].shape[0]):
                if ListMem[i][j] >= sleep_beta[i-1]:
                    ListSpikes[i][j] = 1
                else:
                    ListSpikes[i][j] = 0

            post_1 = []  
            pre_1 = []
            pre_0 = []
#           STDP
            for j in range(ListSpikes[i].shape[0]):
                if ListSpikes[i][j] == 1:
                    print(j)
                    post_1.append(j)                  
            for j in range(ListSpikes[i-1].shape[0]):
                if ListSpikes[i-1][j] == 1:
                    pre_1.append(j)                
                else:
                    pre_0.append(j)

#             print("1",len(post_1))
#             print("2",len(pre_1))
#             print(list(product(post_1,pre_1)))
#             print(len(pre_0))

            for idex in list(product(post_1,pre_1)):
                updateswitch = 1                         
                weight[i-1][idex] = weight[i-1][idex]  - sleep_dec * torch.sigmoid(weight[i-1][idex] )
            for idex in list(product(post_1,pre_0)):
                updateswitch = 1                                                                      
                weight[i-1][idex] = weight[i-1][idex]  + sleep_inc * torch.sigmoid(weight[i-1][idex] )

            print("The status of switch is ",updateswitch)
            if updateswitch == 1:
                if i == 1:
                    changenum +=1
                    fc1_new_weight=torch.nn.Parameter(weight[0])
                    model.fc1.weight = fc1_new_weight
                if i == 2:
                    changenum +=1
                    fc2_new_weight=torch.nn.Parameter(weight[1])
                    model.fc2.weight = fc2_new_weight
                if i == 3:
                    changenum +=1
                    fc3_new_weight=torch.nn.Parameter(weight[2])
                    model.fc3.weight = fc3_new_weight

            updateswitch = 0  #reset switch                  

            #reset
            for j in range(ListSpikes[i].shape[0]):
                if ListSpikes[i][j] == 1:
                    ListMem[i][j] = 0
            
            #To save the memory space, we just see what happened after the weight changed 20 times
            if changenum >= 20:
                print("changenum is ",changenum)
                sys.exit(0)

for data in trainloader:
        # get the inputs
    inputs, labels = data
    inputs = inputs.cuda(device)
    labels = labels.cuda(device)
    sleep(model, torch.t(inputs),1)

loss_function = nn.CrossEntropyLoss()
# live_loss_plot = LiveLossPlot()
optimiser = optim.SGD(model.parameters(), lr=0.1, momentum=0.5)
trial = torchbearer.Trial(model, optimiser, loss_function, metrics=['loss', 'accuracy']).to(device)
trial.with_generators(trainloader, test_generator=testloader)
results = trial.evaluate(data_key=torchbearer.TEST_DATA)
print(results)
torch.save(model,'save_sleep.pkl')