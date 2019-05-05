#! /bin/python
import os
import torch
import torch.nn as nn
from classifier_data_loader import get_data_loaders
from classifier import Classifier
from tensorboardX import SummaryWriter
import time
import numpy as np 
torch.backends.cudnn.benchmark=True
import sys
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
expt_prefix="v4"
tlog, vlog = SummaryWriter("../../"+expt_prefix+"logs/train_pytorch"), SummaryWriter("../../"+expt_prefix+"logs/val_pytorch")
load_path=expt_prefix+"logs/model_dict0.pt"
lp = open("./"+expt_prefix+"log","w+") ## Output log file

class TrainValidate():


    def __init__(self,hiddens=[512,300,150,50],num_epochs=100,initial_lr=1e-3,batch_size=3500,weight_decay=1e-4,load=False):
        self.num_epochs = num_epochs
        self.bs = batch_size
        self.criterion = torch.nn.CrossEntropyLoss(reduction='mean')
        self.net = Classifier().to(device)
        #self.net = torch.nn.DataParallel(self.net,device_ids=[0,1,2,3])
        self.embed_size = 512
        #self.train_loader, self.valid_loader = get_data_loaders()
        self.train_loss = 0.0
        self.valid_loss = 0.0
        self.patience = 1000
        self.lr = initial_lr
        self.optimizer =  torch.optim.Adam(self.net.parameters(),lr=self.lr,weight_decay=weight_decay)
        self.init_epoch = 0
        self.net.apply(self.weights_init)
        if load:
            print('Loading model from past')
            self.init_epoch=self.load(load_path)         
        lp.write(expt_prefix+' Model with hiddens '+str(hiddens)+'\n\n')
        self.run()
  

    def train_validate(self):
        print('Batch size is',self.bs)
        train_loader,valid_loader, test_loader = get_data_loaders(self.bs)
        sch = torch.optim.lr_scheduler.ReduceLROnPlateau(self.optimizer,patience=self.patience,min_lr=1e-7)
        best_loss= np.inf
        for epoch in range(self.init_epoch,self.num_epochs+self.init_epoch):
            tstart=time.time()
            print("-------------------------------------------------------------------------------------------")
            print("Processing epoch "+str(epoch))
            self.train_loss,ftacc,vtacc=self.run_epoch(train_loader) 
            train_acc = 0.5 *(ftacc + vtacc)
            tlog.add_scalar('Train Loss', self.train_loss)
            print('Training Loss is ', self.train_loss, "Training Accuracy",train_acc,"Face Accuracy",ftacc,"Voice Accuracy",vtacc,' Learning Rate is ', self.get_lr())
            self.eval_loss,fvacc,vvacc=self.run_epoch(valid_loader,False)
            valid_acc = 0.5 * (fvacc + vvacc)
            vlog.add_scalar('Validation Loss'+ str(epoch), self.eval_loss)
            print('Validation Loss is ',self.eval_loss,"Validation Accuracy",valid_acc,"Face Accuracy",fvacc,"Voice Accuracy",vvacc)
            tend=time.time()
            print('Epoch ',str(epoch), ' was done in ',str(tend-tstart),' seconds')
            print("-------------------------------------------------------------------------------------------")
            for tag, value in self.net.named_parameters():
                tag = tag.replace('.', '/')
                tlog.add_histogram(tag,value.data,global_step=epoch)
                tlog.add_histogram(tag+'/grad',value.data,global_step=epoch)
            if self.eval_loss < best_loss:
                best_loss = self.eval_loss
                pat = 0
                self.save(epoch)
            else:
                pat += 1
                if pat >= self.patience:
                    print("Early stopping !")
                    break
            sch.step(self.eval_loss)

        print('Training and Validation complete !')

    def get_lr(self):
        for param_group in self.optimizer.param_groups:
            return param_group['lr']

    def save(self,epoch):
        torch.save({'epoch': epoch,
            'model_state_dict': self.net.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'loss': self.train_loss,
            'dev_loss':self.eval_loss},"./"+expt_prefix+"logs/model_dict"+str(epoch)+".pt")
            

    def run_epoch(self,loader,update=True):
        epoch_loss = 0
        start_time = time.time()
        faccu = 0
        vaccu = 0
        for batch_index,(voice_batch,face_batch,class_labels) in enumerate(loader):
            self.optimizer.zero_grad()
           # print('Embedding size',embedding.size())
            face_batch = face_batch.to(device)
            voice_batch = voice_batch.to(device)
            class_labels = class_labels.to(device)
            face_logits = self.net(face_batch)
             ##Net takes voice, faces
            loss = self.criterion(face_logits,class_labels)
            epoch_loss += loss.item()
            fop = torch.nn.functional.Softmax(face_logits,dim=1)
            _,fpred=torch.max(fop,1)
            facc=torch.sum(torch.flatten(fpred==class_labels))
            faccu+= facc.item() 
            if update:
                loss.backward()
                self.optimizer.step()
            voice_logits = self.net(voice_batch,face=False)
            loss = self.criterion(voice_logits,class_labels)
            epoch_loss += loss.item()
            vop = torch.nn.functional.Softmax(voice_logits,dim=1)
            _,vpred=torch.max(vop,1)
            vacc=torch.sum(torch.flatten(vpred==class_labels))
            vaccu+=vacc.item()
            if update:
                loss.backward()
                self.optimizer.step()
            del face_logits,voice_logits,fpred,vpred
        torch.cuda.empty_cache()
        epoch_loss /= (batch_index+1)
        faccu /= (batch_index +1)
        vaccu /= (batch_index +1)
        return epoch_loss,faccu,vaccu

    def load(self,path):
        checkpoint = torch.load(path)
        self.net.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        epoch = checkpoint['epoch']
        self.train_loss= checkpoint['loss']
        self.eval_loss=checkpoint['dev_loss']
        return epoch

    def weights_init(self,m):
        if isinstance(m, nn.BatchNorm2d):
            nn.init.constant_(m.weight, 1)
            nn.init.constant_(m.bias, 0)      
        elif isinstance(m, nn.Linear):
            nn.init.xavier_normal_(m.weight)
            nn.init.constant_(m.bias,0)
    
    def test(self,embedding):
        return self.net(embedding).cpu().numpy()

    def run(self):
        self.train_validate()
        #self.test()

if __name__ == "__main__":
    import multiprocessing
    print('Device is',device)
    TrainValidate()


    



