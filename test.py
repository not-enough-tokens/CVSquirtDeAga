import sys
import cv2

print("hola desde el telefono")
print("Python:", sys.version)
print("OpenCV:", cv2.__version__)
print("Modulo aruco disponible:", hasattr(cv2, "aruco"))