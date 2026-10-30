from onnxruntime.quantization import QuantType, quantize_dynamic


quantize_dynamic(
    model_input="onnx_out/model.onnx",
    model_output="model_int8.onnx",
    weight_type=QuantType.QUInt8,
)
print("Wrote model_int8.onnx")
