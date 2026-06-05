import { ComponentFixture, TestBed } from '@angular/core/testing';

import { UsedByComponent } from './used-by.component';

const mockElement = {
  age: 'Mon, 19 Sep 2022 16:39:10 GMT',
  capacity: '5Gi',
  class: '',
  modes: ['ReadWriteOnce'],
  name: 'a0-new-image-workspace-d8pc2',
  namespace: 'kubeflow-user',
  notebooks: ['a0-new-image'],
  containers: ['a0-container'],
  status: {
    message: 'Bound',
    phase: 'ready',
    state: '',
  },
  viewer: 'uninitialized',
};

describe('UsedByComponent', () => {
  let component: UsedByComponent;
  let fixture: ComponentFixture<UsedByComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [UsedByComponent],
    }).compileComponents();
  });

  beforeEach(() => {
    fixture = TestBed.createComponent(UsedByComponent);
    component = fixture.componentInstance;
    component.element = mockElement;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should link notebooks and containers to their details pages', () => {
    expect(component.usedByItems).toEqual([
      {
        name: 'a0-new-image',
        url: '/jupyter/notebook/details/kubeflow-user/a0-new-image',
      },
      {
        name: 'a0-container',
        url: '/jupyter/container/details/kubeflow-user/a0-container',
      },
    ]);
  });
});
