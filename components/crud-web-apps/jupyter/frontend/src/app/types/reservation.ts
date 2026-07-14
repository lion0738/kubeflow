export interface ReservedResourceAvailability {
  node_id: string;
  cpu_count: number;
  gpu_count: number;
  memory_size: number;
  remaining_cpu_count: number;
  remaining_gpu_count: number;
  remaining_memory_size: number;
}
