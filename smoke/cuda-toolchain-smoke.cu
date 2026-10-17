#include <cuda_fp16.h>
__global__ void check(half *x) { x[0] = __float2half(1.0f); }
