import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { FormModule as KfFormModule } from 'kubeflow';
import { FormCommandComponent } from './form-command.component';

@NgModule({
  declarations: [FormCommandComponent],
  imports: [
    CommonModule,
    KfFormModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
  ],
  exports: [FormCommandComponent],
})
export class FormCommandModule {}
  