import { CommonModule } from '@angular/common';
import { NgModule } from '@angular/core';
import { FormModule as KfFormModule } from 'kubeflow';
import { FormReservedResourcesComponent } from './form-reserved-resources.component';

@NgModule({
  declarations: [FormReservedResourcesComponent],
  imports: [CommonModule, KfFormModule],
  exports: [FormReservedResourcesComponent],
})
export class FormReservedResourcesModule {}
