import os
import logging
from typing import Dict, Any, Optional
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)


class YoloPotholeDetector:
    _instance: Optional["YoloPotholeDetector"] = None

    def __init__(self, model_path: str = settings.YOLO_MODEL_PATH):
        self.model_path = model_path
        self.model = None
        self.is_loaded = False
        self.load_error: Optional[str] = None
        self._load_model()

    @classmethod
    def get_instance(cls) -> "YoloPotholeDetector":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_model(self):
        """Loads Ultralytics YOLO model from model_path if available."""
        try:
            from ultralytics import YOLO

            if os.path.exists(self.model_path):
                logger.info(f"Loading custom pothole YOLO model from {self.model_path}")
                self.model = YOLO(self.model_path)
                self.is_loaded = True
            else:
                logger.warning(
                    f"Custom pothole model not found at '{self.model_path}'. "
                    f"Attempting to load default yolov8n.pt for architecture validation..."
                )
                try:
                    self.model = YOLO("yolov8n.pt")
                    self.is_loaded = True
                    logger.info("Loaded yolov8n.pt as baseline architecture.")
                except Exception as ex:
                    self.load_error = str(ex)
                    logger.warning(f"Could not load baseline yolov8n: {ex}")
        except ImportError:
            self.load_error = "ultralytics package not installed"
            logger.warning("ultralytics package not installed. Running in diagnostic mode.")
        except Exception as e:
            self.load_error = str(e)
            logger.error(f"Error initializing YOLO model: {e}")

    def detect_potholes(self, image_path: str) -> Dict[str, Any]:
        """
        Runs YOLO inference on the given image.
        Returns:
            dict containing:
            - highest_confidence: float (0.0 - 1.0)
            - detection_result: str (label of detected class)
            - passed_threshold: bool (whether highest_confidence >= POTHOLE_CONFIDENCE_THRESHOLD)
            - raw_boxes: list of detected bounding boxes and confidences
            - model_status: information on the active model
        """
        threshold = settings.POTHOLE_CONFIDENCE_THRESHOLD

        if not self.is_loaded or self.model is None:
            # Model file missing or runtime issue: handle gracefully without fabricating scores
            logger.warning(f"YOLO model not loaded ({self.load_error}). Returning unconfirmed detection.")
            return {
                "highest_confidence": 0.0,
                "detection_result": "no_pothole_detected",
                "passed_threshold": False,
                "raw_boxes": [],
                "model_status": f"Model uninitialized: {self.load_error or 'Weights file not found'}",
                "threshold_applied": threshold,
            }

        try:
            # Run real YOLO inference
            results = self.model.predict(source=image_path, conf=0.1, verbose=False)
            
            pothole_confidences = []
            boxes_info = []

            for r in results:
                names = r.names
                for box in r.boxes:
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    cls_name = names.get(cls_id, f"class_{cls_id}").lower()

                    boxes_info.append({
                        "class": cls_name,
                        "confidence": round(conf, 4),
                        "xywh": box.xywh[0].tolist() if hasattr(box, "xywh") else [],
                    })

                    # If model has class 'pothole', prioritize it;
                    # If fine-tuned model class 0 is pothole, record it
                    if "pothole" in cls_name or cls_id == 0:
                        pothole_confidences.append(conf)

            highest_conf = max(pothole_confidences) if pothole_confidences else 0.0
            highest_conf = round(highest_conf, 4)
            passed = highest_conf >= threshold

            return {
                "highest_confidence": highest_conf,
                "detection_result": "pothole" if passed else ("pothole_candidate" if highest_conf > 0 else "no_pothole_detected"),
                "passed_threshold": passed,
                "raw_boxes": boxes_info,
                "model_status": "active",
                "threshold_applied": threshold,
            }

        except Exception as e:
            logger.error(f"Inference error on {image_path}: {e}")
            return {
                "highest_confidence": 0.0,
                "detection_result": "processing_error",
                "passed_threshold": False,
                "raw_boxes": [],
                "model_status": f"Inference error: {str(e)}",
                "threshold_applied": threshold,
            }
