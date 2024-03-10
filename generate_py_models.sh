#!/bin/bash
python  -m grpc_tools.protoc -I ./ \
        --python_out=./arm/proto --pyi_out=./arm/proto \
        ./API_SIM.proto \
        --protobuf-to-pydantic_out=./arm/proto
python  ./arm/proto/do_imports.py ./arm/proto/API_SIM_p2p.py