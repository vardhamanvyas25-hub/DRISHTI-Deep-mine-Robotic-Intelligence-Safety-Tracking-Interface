import cv2
import numpy as np
from ultralytics import YOLO

class HazardDetector:
    def __init__(self, model_name="yolov8n.pt", conf_thresh=0.40):
        """
        Initializes lightweight YOLO model (YOLOv8 Nano is optimized for edge/Pi deployment).
        """
        self.model = YOLO(model_name)
        self.conf_thresh = conf_thresh

    def process_frame(self, frame):
        """
        Runs object detection on an OpenCV frame.
        
        Returns:
            annotated_frame (np.ndarray): Frame with bounding boxes drawn.
            detections (list): Extracted detections [{'class': 'person', 'confidence': 0.85}]
        """
        if frame is None:
            return None, []

        # Run inference
        results = self.model(frame, conf=self.conf_thresh, verbose=False)[0]
        
        # Render bounding boxes onto frame
        annotated_frame = results.plot()

        # Parse detected objects
        detections = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            class_name = self.model.names[cls_id]
            confidence = float(box.conf[0])

            detections.append({
                "class": class_name,
                "confidence": round(confidence, 2)
            })

        return annotated_frame, detections