import { TestBed } from '@angular/core/testing';
import {
  HttpClientTestingModule,
  HttpTestingController,
} from '@angular/common/http/testing';
import { SnackBarService } from 'kubeflow';
import { JWABackendService } from './backend.service';

const SnackBarServiceStub: Partial<SnackBarService> = {
  open: () => {},
  close: () => {},
};

describe('JWABackendService', () => {
  let service: JWABackendService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [{ provide: SnackBarService, useValue: SnackBarServiceStub }],
    }).compileComponents();
    service = TestBed.inject(JWABackendService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });

  it('should get notebook ports', () => {
    service.getNotebookPorts('ns1', 'nb1').subscribe(ports => {
      expect(ports.length).toBe(1);
      expect(ports[0].name).toBe('nodeport-service-nb1-8080');
    });

    const req = http.expectOne('api/namespaces/ns1/notebooks/nb1/ports');
    expect(req.request.method).toBe('GET');
    req.flush({
      ports: [
        {
          name: 'nodeport-service-nb1-8080',
          port: 8080,
          targetPort: 8080,
          nodePort: 30080,
          protocol: 'TCP',
          type: 'NodePort',
        },
      ],
    });
  });

  it('should create notebook ports', () => {
    service
      .createNotebookPort('ns1', 'nb1', {
        port: 8080,
        nodePort: 30080,
        protocol: 'TCP',
      })
      .subscribe(port => {
        expect(port.nodePort).toBe(30080);
      });

    const req = http.expectOne('api/namespaces/ns1/notebooks/nb1/ports');
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({
      port: 8080,
      nodePort: 30080,
      protocol: 'TCP',
    });
    req.flush({
      port: {
        name: 'nodeport-service-nb1-8080',
        port: 8080,
        targetPort: 8080,
        nodePort: 30080,
        protocol: 'TCP',
        type: 'NodePort',
      },
    });
  });

  it('should update container ports', () => {
    service
      .updateContainerPort('ns1', 'container1', 'svc1', {
        port: 9090,
        protocol: 'UDP',
      })
      .subscribe(port => {
        expect(port.port).toBe(9090);
      });

    const req = http.expectOne(
      'api/namespaces/ns1/containers/container1/ports/svc1',
    );
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ port: 9090, protocol: 'UDP' });
    req.flush({
      port: {
        name: 'svc1',
        port: 9090,
        targetPort: 9090,
        nodePort: 30090,
        protocol: 'TCP',
        type: 'NodePort',
      },
    });
  });

  it('should delete container ports', () => {
    service.deleteContainerPort('ns1', 'container1', 'svc1').subscribe();

    const req = http.expectOne(
      'api/namespaces/ns1/containers/container1/ports/svc1',
    );
    expect(req.request.method).toBe('DELETE');
    req.flush({});
  });
});
