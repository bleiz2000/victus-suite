#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <unistd.h>
#include <sys/resource.h>
#include <cuda_runtime.h>

#define BLOCK 256
#define GRID 96
#define ROW 250000

__global__ void burn(float *out, int iters)
{
	unsigned i = blockIdx.x * blockDim.x + threadIdx.x;
	float x = 1.0f + (i % 997) * 0.001f;
	float y = 1.0000013f;
	for (int k = 0; k < iters; k++) {
		x = x * y + 1.0000001e-7f;
		y = y * x + 2.0000002e-7f;
		x = sqrtf(x) * 0.999999f + 1e-5f;
	}
	out[i] = x + y;
}

static double now_s(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec / 1e9;
}

static void nap(double sec)
{
	if (sec <= 0)
		return;
	struct timespec ts;
	ts.tv_sec = (time_t)sec;
	ts.tv_nsec = (long)((sec - ts.tv_sec) * 1e9);
	nanosleep(&ts, NULL);
}

/* gpuload <seconds> <duty%>  — duty 100 = непрерывно, 50 = пауза = работа */
int main(int argc, char **argv)
{
	double secs = 30.0;
	int duty = 100;
	if (argc > 1)
		secs = atof(argv[1]);
	if (argc > 2)
		duty = atoi(argv[2]);
	if (secs < 1.0)
		secs = 1.0;
	if (duty < 5)
		duty = 5;
	if (duty > 100)
		duty = 100;

	nice(19);

	cudaError_t e = cudaSetDevice(0);
	if (e != cudaSuccess) {
		fprintf(stderr, "cudaSetDevice: %s\n", cudaGetErrorString(e));
		return 1;
	}
	float *d = nullptr;
	e = cudaMalloc(&d, GRID * BLOCK * sizeof(float));
	if (e != cudaSuccess) {
		fprintf(stderr, "cudaMalloc: %s\n", cudaGetErrorString(e));
		return 1;
	}

	double ON = 0.020;
	double OFF = ON * (100.0 - duty) / (double)duty;
	double end = now_s() + secs;
	long rows = 0;
	while (now_s() < end) {
		double block_end = now_s() + ON;
		while (now_s() < block_end && now_s() < end) {
			burn<<<GRID, BLOCK>>>(d, ROW);
			e = cudaGetLastError();
			if (e != cudaSuccess) {
				fprintf(stderr, "launch: %s\n", cudaGetErrorString(e));
				goto out;
			}
			e = cudaDeviceSynchronize();
			if (e != cudaSuccess) {
				fprintf(stderr, "sync: %s\n", cudaGetErrorString(e));
				goto out;
			}
			rows++;
		}
		if (duty < 100)
			nap(OFF);
	}
out:
	cudaFree(d);
	fprintf(stderr, "gpuburn: %.0fs duty=%d%% done, %ld rows\n", secs, duty, rows);
	return 0;
}
