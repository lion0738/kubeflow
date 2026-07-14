import { FormBuilder } from '@angular/forms';
import { of } from 'rxjs';
import { PortsComponent } from './ports.component';

describe('PortsComponent', () => {
  const backend = {
    getConfig: () => of({}),
  } as any;
  const snackBar = { open: () => undefined } as any;
  let component: PortsComponent;

  beforeEach(() => {
    component = new PortsComponent(new FormBuilder(), backend, snackBar);
  });

  it('requires a valid lowercase domain for Gateway access', () => {
    component.form.patchValue({ accessType: 'Gateway', domain: 'Bad_Domain' });
    expect(component.form.get('domain')?.hasError('pattern')).toBeTrue();

    component.form.patchValue({ domain: 'web-api' });
    expect(component.form.get('domain')?.valid).toBeTrue();
  });

  it('previews one URL for a shared Gateway exposure', () => {
    component.form.patchValue({ accessType: 'Gateway', domain: 'abc' });
    expect(component.previewUrls).toEqual([
      'https://abc.knu-kubeflow.duckdns.org',
    ]);
  });

  it('previews each StatefulSet ordinal when per-replica is enabled', () => {
    component.isContainer = true;
    component.replicas = 3;
    component.form.patchValue({
      accessType: 'Gateway',
      domain: 'abc',
      perReplica: true,
    });

    expect(component.previewUrls).toEqual([
      'https://abc-0.knu-kubeflow.duckdns.org',
      'https://abc-1.knu-kubeflow.duckdns.org',
      'https://abc-2.knu-kubeflow.duckdns.org',
    ]);
  });

  it('does not send per-replica mode for a Notebook', () => {
    component.isContainer = false;
    component.form.patchValue({
      accessType: 'Gateway',
      domain: 'abc',
      perReplica: true,
      port: 8000,
    });

    const payload = (component as any).payload();
    expect(payload.perReplica).toBeFalse();
    expect(payload.protocol).toBe('TCP');
  });
});
