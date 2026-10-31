"""Count ORB keypoints inside the copied patch, to see whether the detector
has enough features to match. Run from the project root."""

import cv2
import numpy as np

from app import fixtures

clean = fixtures.recompress(fixtures.scene(1), quality=95)
gray = np.asarray(clean.convert("L"))
orb = cv2.ORB_create(nfeatures=1500, fastThreshold=20)
keypoints, _ = orb.detectAndCompute(gray, None)


def inside(pt, x0, y0, x1, y1):
    return x0 <= pt[0] < x1 and y0 <= pt[1] < y1


print("total keypoints:", len(keypoints))
print("inside source patch (60-156):", sum(inside(k.pt, 60, 60, 156, 156) for k in keypoints))
print("inside pasted copy (368-464, 288-384):", sum(inside(k.pt, 368, 288, 464, 384) for k in keypoints))