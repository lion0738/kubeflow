import { CommonModule } from '@angular/common';
import { HttpClientModule } from '@angular/common/http';
import { ComponentFixture, TestBed, waitForAsync } from '@angular/core/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { RouterTestingModule } from '@angular/router/testing';
import {
  FormModule as KfFormModule,
  NamespaceService,
  SnackBarService,
  TitleActionsToolbarModule,
} from 'kubeflow';
import { of } from 'rxjs';
import { JWABackendService } from 'src/app/services/backend.service';
import { FormAffinityTolerationsModule } from './form-affinity-tolerations/form-affinity-tolerations.module';
import { FormConfigurationsModule } from './form-configurations/form-configurations.module';
import { FormCpuRamModule } from './form-cpu-ram/form-cpu-ram.module';
import { FormDataVolumesModule } from './form-data-volumes/form-data-volumes.module';
import { FormEnvironmentVariablesModule } from './form-environment-variables/form-environment-variables.module';
import { FormGpusModule } from './form-gpus/form-gpus.module';
import { FormImageModule } from './form-image/form-image.module';
import { FormNameModule } from './form-name/form-name.module';
import { FormNewContainerComponent } from './form-new-container.component';
import { VolumeModule } from './volume/volume.module';

const JWABackendServiceStub = {
  getConfig: () => of({}),
  createContainer: () => of(),
  getGPUVendors: () => of(),
  getStorageClasses: () => of(),
  getDefaultStorageClass: () => of(),
};

const NamespaceServiceStub = {
  getSelectedNamespace: () => of(),
  getSelectedNamespace2: () => of('kubeflow-user'),
};

const SnackBarServiceStub = {
  open: () => {},
  close: () => {},
};

describe('FormNewContainerComponent', () => {
  let component: FormNewContainerComponent;
  let fixture: ComponentFixture<FormNewContainerComponent>;

  beforeEach(
    waitForAsync(() => {
      TestBed.configureTestingModule({
        declarations: [FormNewContainerComponent],
        imports: [
          CommonModule,
          KfFormModule,
          TitleActionsToolbarModule,
          VolumeModule,
          FormDataVolumesModule,
          FormCpuRamModule,
          FormGpusModule,
          FormConfigurationsModule,
          FormAffinityTolerationsModule,
          FormImageModule,
          FormNameModule,
          HttpClientModule,
          RouterTestingModule,
          NoopAnimationsModule,
          FormEnvironmentVariablesModule,
        ],
        providers: [
          { provide: JWABackendService, useValue: JWABackendServiceStub },
          { provide: NamespaceService, useValue: NamespaceServiceStub },
          { provide: SnackBarService, useValue: SnackBarServiceStub },
        ],
      }).compileComponents();
    }),
  );

  beforeEach(() => {
    fixture = TestBed.createComponent(FormNewContainerComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
