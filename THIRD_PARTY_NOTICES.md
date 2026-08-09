# Third-party notices

Offline Background Remover is MIT-licensed, but it depends on third-party
software and model artifacts that retain their own licenses.

## U²-Net

The background-removal models are based on **U²-Net: Going Deeper with Nested
U-Structure for Salient Object Detection** by Xuebin Qin, Zichen Zhang,
Chenyang Huang, Masood Dehghan, Osmar R. Zaiane, and Martin Jagersand.

- Project: <https://github.com/xuebinqin/U-2-Net>
- Project license: Apache License 2.0
- Paper: <https://arxiv.org/abs/2005.09007>

Model artifacts are downloaded from the public model assets maintained by the
`rembg` project and are not stored in this Git repository.

## rembg

`rembg` is used as a development/test dependency for backend equivalence checks
and as the upstream host for the pinned U²-Net ONNX artifacts.

- Project: <https://github.com/danielgatis/rembg>
- License: MIT

## Runtime packages

The application also uses Pillow, NumPy, ONNX Runtime DirectML,
tkinterdnd2, and OpenCV. Distribution builds must retain all notices required
by the versions listed in `requirements.txt`. PyInstaller and development/test
dependencies are governed by their respective licenses.
