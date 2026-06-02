export interface PortObject {
  name: string;
  port: number;
  targetPort: number | string;
  nodePort: number;
  protocol: string;
  type: string;
}

export interface PortRequest {
  port: number;
  nodePort?: number;
}
