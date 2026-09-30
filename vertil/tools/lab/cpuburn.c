#define _GNU_SOURCE
#include <math.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>

static volatile double g_sink = 1.0;
static double g_end;

static double now_s(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec / 1e9;
}

static void *worker(void *arg)
{
	(void)arg;
	nice(19);
	double a = 1.000001, b = 0.9999993;
	while (now_s() < g_end) {
		for (int i = 0; i < 20000; i++) {
			a = a * b + 1.0000001e-7;
			b = b * a + 1.0000002e-7;
			if (a > 1e6 || b > 1e6) {
				a = 1.000001;
				b = 0.9999993;
			}
		}
		g_sink = a + b;
	}
	return NULL;
}

int main(int argc, char **argv)
{
	int n = 8;
	double secs = 30.0;
	if (argc > 1)
		n = atoi(argv[1]);
	if (argc > 2)
		secs = atof(argv[2]);
	if (n < 1)
		n = 1;
	if (n > 64)
		n = 64;
	if (secs < 1.0)
		secs = 1.0;

	nice(19);
	g_end = now_s() + secs;

	pthread_t t[64];
	for (int i = 0; i < n; i++)
		if (pthread_create(&t[i], NULL, worker, NULL))
			return 1;
	for (int i = 0; i < n; i++)
		pthread_join(t[i], NULL);

	fprintf(stderr, "cpuburn: %d threads x %.0fs done sink=%.6f\n", n, secs, g_sink);
	return 0;
}
