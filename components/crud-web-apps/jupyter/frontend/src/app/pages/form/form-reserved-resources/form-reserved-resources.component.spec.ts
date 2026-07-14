import { ComponentFixture, TestBed, waitForAsync } from '@angular/core/testing';
import { of } from 'rxjs';
import { JWABackendService } from 'src/app/services/backend.service';
import { FormReservedResourcesComponent } from './form-reserved-resources.component';
import { FormReservedResourcesModule } from './form-reserved-resources.module';

const JWABackendServiceStub = {
  getReservedResourceAvailability: jasmine
    .createSpy('getReservedResourceAvailability')
    .and.returnValue(
      of([
        {
          node_id: 'node-1',
          cpu_count: 8,
          gpu_count: 2,
          memory_size: 32,
          remaining_cpu_count: 4,
          remaining_gpu_count: 1,
          remaining_memory_size: 16,
        },
      ]),
    ),
};

describe('FormReservedResourcesComponent', () => {
  let component: FormReservedResourcesComponent;
  let fixture: ComponentFixture<FormReservedResourcesComponent>;

  beforeEach(
    waitForAsync(() => {
      TestBed.configureTestingModule({
        imports: [FormReservedResourcesModule],
        providers: [
          { provide: JWABackendService, useValue: JWABackendServiceStub },
        ],
      }).compileComponents();
    }),
  );

  beforeEach(() => {
    fixture = TestBed.createComponent(FormReservedResourcesComponent);
    component = fixture.componentInstance;
    component.namespace = 'kubeflow-user';
    fixture.detectChanges();
  });

  it('should load reserved resources for the namespace', () => {
    expect(component.resources.length).toBe(1);
    expect(component.resources[0].node_id).toBe('node-1');
    expect(
      JWABackendServiceStub.getReservedResourceAvailability,
    ).toHaveBeenCalledWith('kubeflow-user');
  });
});
