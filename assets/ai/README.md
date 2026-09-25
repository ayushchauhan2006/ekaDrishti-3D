# AI model assets

EkaDrishti uses the standard YOLOv4-tiny COCO network through OpenCV DNN for dynamic-object masking.

| File | Purpose |
|---|---|
| `yolov4-tiny.cfg` | Darknet network configuration |
| `yolov4-tiny.weights` | Pretrained COCO weights |
| `coco.names` | COCO class labels |

Sources: the AlexeyAB Darknet repository and its published YOLOv4-tiny release asset. The current SHA-256 values are recorded here for reproducibility:

```text
f858e3724962eedf3ac44e3b6cb3f0c3d9ed067c306bb831f539c578b924c90e  yolov4-tiny.cfg
cf9fbfd0f6d4869b35762f56100f50ed05268084078805f0e7989efe5bb8ca87  yolov4-tiny.weights
634a1132eb33f8091d60f2c346ababe8b905ae08387037aed883953b7329af84  coco.names
```

The runtime default is confidence 0.50 with NMS 0.45. Only people, common vehicles and animals are masked. Every mission receives a per-frame `ai_mask_report.json`; an empty detection result is retained as an audit result rather than being presented as an AI modification.
