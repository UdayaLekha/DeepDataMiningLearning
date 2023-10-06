import torch
#https://debuggercafe.com/anchor-free-object-detection-inference-using-fcos-fully-connected-one-stage-object-detection/

import cv2
import torch
import argparse
import time
import torchvision
from torchvision.models import get_model, get_model_weights, get_weight, list_models
from torchvision.io.image import read_image
from torchvision.utils import draw_bounding_boxes
from torchvision.transforms.functional import to_pil_image
from DeepDataMiningLearning.detection.models import create_detectionmodel, get_torchvision_detection_models, load_trained_model
import numpy as np

def myread_image(preprocess, imgpath, usecv2=True, uspil=False):
    if usecv2==True:
        im0 = cv2.imread(imgpath) #(1080, 810, 3) HWC, BGR format
        imaglist = [im0]
        imgtensors = preprocess(imaglist) #return #[1, 3, 640, 480]
        return imgtensors, imaglist #for yolo
    else:
        img = read_image(imgpath)
        batch = [preprocess(img)]
        return batch, [img] #for faster rcnn

def savepred_toimage(im0, onedetection, classes=None, usecv2=True, boxformat='xyxy', resultfile="results.jpg"):
    #labels = [names[i] for i in detections["labels"]] #classes[i]
    #img=im0.copy() #HWC (1080, 810, 3)
    if usecv2:
        im0=im0[..., ::-1].transpose((2,0,1))  # BGR to RGB, HWC to CHW
    imgtensor = torch.from_numpy(im0.copy()) #[3, 1080, 810]
    if boxformat =='xyxy':
        pred_bbox_tensor=onedetection["boxes"] #torch.from_numpy(onedetection["boxes"])
    else:
        #pred_bbox_tensor=torchvision.ops.box_convert(torch.from_numpy(onedetection["boxes"]), 'xywh', 'xyxy')
        pred_bbox_tensor=torchvision.ops.box_convert(onedetection["boxes"], 'xywh', 'xyxy')
    
    #print(pred_bbox_tensor)
    pred_labels = onedetection["labels"].numpy().astype(int).tolist()
    if classes:
        labels = [classes[i] for i in pred_labels]
    else:
        labels = [str(i) for i in pred_labels]
    #img: Tensor of shape (C x H x W) and dtype uint8.
    #box: Tensor of size (N, 4) containing bounding boxes in (xmin, ymin, xmax, ymax) format.
    #labels: Optional[List[str]]
    box = draw_bounding_boxes(imgtensor, boxes=pred_bbox_tensor,
                            labels=labels,
                            colors="red",
                            width=4, font_size=50)
    im = to_pil_image(box.detach())
    # save a image using extension
    im = im.save(resultfile)
    return im

def multimodel_inference(modelname, imgpath, ckpt_file, device='cuda:0', scale='n'):

    model, imgtransform, classes = create_detectionmodel(modelname=modelname, num_classes=80, trainable_layers=0, ckpt_file = ckpt_file, fp16=False, device= device, scale='n')

    if modelname.startswith("yolo"):
        imgtensors, imaglist = myread_image(imgtransform, imgpath, usecv2=True)
    else:
        imgtensors, imaglist= myread_image(imgtransform, imgpath, usecv2=False)
    #inference
    preds = model(imgtensors)
    
    newimgsize = imgtensors.shape[2:] #640, 480
    origimageshapes=[img.shape for img in imaglist]
    detections = imgtransform.postprocess(preds, newimgsize, origimageshapes)

    idx=0
    onedetection = detections[idx]
    im0=imaglist[idx]
    savepred_toimage(im0, onedetection, classes=classes, usecv2=True, boxformat='xyxy', resultfile="results.jpg")

def test_inference(modelname, imgpath):
    img = read_image(imgpath)
    pretrained_model, preprocess, weights, classes = get_torchvision_detection_models(modelname)
    pretrained_model.eval()
    #Apply inference preprocessing transforms
    batch = [preprocess(img)]
    prediction = pretrained_model(batch)[0]
    labels = [classes[i] for i in prediction["labels"]]
    box = draw_bounding_boxes(img, boxes=prediction["boxes"],
                            labels=labels,
                            colors="red",
                            width=4, font_size=40)
    im = to_pil_image(box.detach())
    return im

def inference_trainedmodel(modelname, num_classes, classes, checkpointpath, imgpath):
    img = read_image(imgpath)
    model, preprocess = load_trained_model(modelname, num_classes, checkpointpath)
    #Apply inference preprocessing transforms
    batch = [preprocess(img)]
    prediction = model(batch)[0]
    print(prediction["labels"])
    print(prediction["boxes"])
    if classes and len(classes)==num_classes:
        labels = [classes[i] for i in prediction["labels"]]
    else:
        labels = [i for i in prediction["labels"]]
    box = draw_bounding_boxes(img, boxes=prediction["boxes"],
                            labels=labels,
                            colors="red",
                            width=4, font_size=40)
    im = to_pil_image(box.detach())
    return im


def detect_video(args):
    # Define the computation device.
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = get_model(device)
    cap = cv2.VideoCapture(args['input'])
    if (cap.isOpened() == False):
        print('Error while trying to read video. Please check path again')
    # Get the frame width and height.
    frame_width = int(cap.get(3))
    frame_height = int(cap.get(4))
    save_name = f"{args['input'].split('/')[-1].split('.')[0]}_{''.join(str(args['threshold']).split('.'))}"
    # Define codec and create VideoWriter object .
    out = cv2.VideoWriter(f"outputs/{save_name}.mp4", 
                        cv2.VideoWriter_fourcc(*'mp4v'), 30, 
                        (frame_width, frame_height))
    frame_count = 0 # To count total frames.
    total_fps = 0 # To get the final frames per second.

    # Read until end of video.
    while(cap.isOpened):
        # Capture each frame of the video.
        ret, frame = cap.read()
        if ret:
            frame_copy = frame.copy()
            frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_BGR2RGB)
            # Get the start time.
            start_time = time.time()
            with torch.no_grad():
                # Get predictions for the current frame.
                boxes, classes, labels = predict(
                    frame, model, 
                    device, args['threshold']
                )
            
            # Draw boxes and show current frame on screen.
            image = draw_boxes(boxes, classes, labels, frame)
            # Get the end time.
            end_time = time.time()
            # Get the fps.
            fps = 1 / (end_time - start_time)
            # Add fps to total fps.
            total_fps += fps
            # Increment frame count.
            frame_count += 1
            # Write the FPS on the current frame.
            cv2.putText(image, f"{fps:.3f} FPS", (15, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        1, (0, 255, 0), 2)
            # Convert from BGR to RGB color format.
            cv2.imshow('image', image)
            out.write(image)
            # Press `q` to exit.
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        else:
            break
    # Release VideoCapture().
    cap.release()
    # Close all frames and video windows.
    cv2.destroyAllWindows()
    # Calculate and print the average FPS.
    avg_fps = total_fps / frame_count
    print(f"Average FPS: {avg_fps:.3f}")


def predict(image, model, device, transform, class_names, detection_threshold):
    """
    Predict the output of an image after forward pass through
    the model and return the bounding boxes, class names, and 
    class labels. 
    """
    # Transform the image to tensor.
    image = transform(image).to(device)
    # Add a batch dimension.
    image = image.unsqueeze(0) 
    # Get the predictions on the image.
    with torch.no_grad():
        outputs = model(image) 
    # Get score for all the predicted objects.
    pred_scores = outputs[0]['scores'].detach().cpu().numpy()
    # Get all the predicted bounding boxes.
    pred_bboxes = outputs[0]['boxes'].detach().cpu().numpy()
    # Get boxes above the threshold score.
    boxes = pred_bboxes[pred_scores >= detection_threshold].astype(np.int32)
    labels = outputs[0]['labels'][:len(boxes)]
    # Get all the predicited class names.
    pred_classes = [class_names[i] for i in labels.cpu().numpy()]
    return boxes, pred_classes, labels

def draw_boxes(boxes, classes, labels, image):
    """
    Draws the bounding box around a detected object.
    """
    for i, box in enumerate(boxes):
        color = 'r' #COLORS[labels[i]]
        cv2.rectangle(
            image,
            (int(box[0]), int(box[1])),
            (int(box[2]), int(box[3])),
            color[::-1], 2
        )
        cv2.putText(image, classes[i], (int(box[0]), int(box[1]-5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color[::-1], 2, 
                    lineType=cv2.LINE_AA)
    return image

# Construct the argument parser.
parser = argparse.ArgumentParser()
parser.add_argument('-i', '--input', default='input/video_1.mp4', 
                    help='path to input video')
parser.add_argument('-t', '--threshold', default=0.5, type=float,
                    help='detection threshold')
args = vars(parser.parse_args())

def main(args):
    #modelname = 'fasterrcnn_resnet50_fpn_v2'
    imgpath = "../../sampledata/sjsupeople.jpg"
    #im=test_inference(modelname, imgpath)
    #im.save("../../data/testinference.png", "PNG")

    modelname = 'yolov8'
    imgpath = './sampledata/bus.jpg'
    ckpt_file = '/data/cmpe249-fa23/modelzoo/yolov8n_statedicts.pt'
    device = 'cuda:0'
    multimodel_inference(modelname, imgpath, ckpt_file, device, scale='n')

if __name__ == "__main__":
    main(args)