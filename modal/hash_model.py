import os
import torch
import logging
import torch.nn as nn

from model.model import build_model
from utils import get_logger, get_summary_writer


class LinearHash(nn.Module):

    def __init__(self, inputDim=2048, outputDim=64):
        super(LinearHash, self).__init__()
        self.fc = nn.Linear(inputDim, outputDim)
        self.drop_out = nn.Dropout(p=0.2)
    
    def forward(self, data):
        result = self.fc(data)
        return torch.tanh(self.drop_out(result))


class Pre_Layer(nn.Module):
    def __init__(self, inputdim=2048, nb_class=64):
        super(Pre_Layer, self).__init__()
        self.fc = nn.Linear(inputdim, nb_class)

    def forward(self, data):
        pre = self.fc(data)
        return pre


class DNPH_M(nn.Module):

    def __init__(self, 
                outputDim=64,
                num_classes=80,
                clipPath="./ViT-B-32.pt", 
                writer=None, 
                saveDir="./result/log", 
                logger: logging.Logger=None, 
                is_train=True):
        super(DNPH_M, self).__init__()
        os.makedirs(saveDir, exist_ok=True)
        self.logger = logger if logger is not None else get_logger(os.path.join(saveDir, "train.log" if is_train else "test.log"))
        self.writer = writer if writer is not None and is_train else get_summary_writer(os.path.join(saveDir, "tensorboard"))
        embedDim, self.clip = self.load_clip(clipPath)

        self.image_hash = LinearHash(inputDim=embedDim, outputDim=outputDim)
        self.text_hash = LinearHash(inputDim=embedDim, outputDim=outputDim)

        self.image_pre = Pre_Layer(inputdim=embedDim, nb_class=num_classes)
        self.text_pre = Pre_Layer(inputdim=embedDim, nb_class=num_classes)

    def freezen(self):
        for name, param in self.clip.named_parameters():
            # print(name)
            if name.find("ln_final.") == 0 or name.find("text_projection") == 0 or name.find("logit_scale") == 0 \
                                        or name.find("visual.ln_post.") == 0 or name.find("visual.proj") == 0:
                # print("1")
                continue
            elif name.find("visual.transformer.resblocks.") == 0 or name.find("transformer.resblocks.") == 0:
                layer_num = int(name.split(".resblocks.")[1].split(".")[0])
                if layer_num >= 12:
                    # print("2")
                    continue
            if name.find("conv2.") == 0:
                # print("3")
                continue
            else:
                # paramenters which < freeze_layer_num will be freezed
                param.requires_grad = False

    def load_clip(self, clipPath: str) -> tuple:
        try:
            model = torch.jit.load(clipPath, map_location="cpu").eval()
            state_dict = model.state_dict()
        except RuntimeError:
            state_dict = torch.load(clipPath, map_location="cpu")
        
        return state_dict["text_projection"].shape[1], build_model(state_dict)

    def encode_image(self, image):
        image_fea = self.clip.encode_image(image) #512

        image_embed = self.image_hash(image_fea)
        image_pre = self.image_pre(image_fea)

        return image_embed, image_pre
    
    def eval(self):
        self.image_hash.eval()
        self.text_hash.eval()
        # self.clip.eval()

    def train(self):
        self.image_hash.train()
        self.text_hash.train()
    
    def encode_text(self, text):
        text_fea = self.clip.encode_text(text)

        text_embed = self.text_hash(text_fea)
        text_pre = self.text_pre(text_fea)

        return text_embed, text_pre

    def forward(self, image, text):
        image_embed, image_pre = self.encode_image(image)
        text_embed, text_pre = self.encode_text(text)
        return image_embed, image_pre, text_embed, text_pre

