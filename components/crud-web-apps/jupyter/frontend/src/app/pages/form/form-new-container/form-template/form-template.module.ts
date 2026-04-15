import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { FormModule as KfFormModule } from 'kubeflow';
import { FormTemplateComponent } from './form-template.component';

@NgModule({
  declarations: [FormTemplateComponent],
  imports: [
    CommonModule,
    KfFormModule,
    MatFormFieldModule,
    MatSelectModule,
  ],
  exports: [FormTemplateComponent],
})
export class FormTemplateModule {}
