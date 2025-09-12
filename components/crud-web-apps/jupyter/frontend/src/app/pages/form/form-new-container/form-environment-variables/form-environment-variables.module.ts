import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule } from '@angular/forms';
import { FormModule as KfFormModule } from 'kubeflow';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

import { FormEnvironmentVariablesComponent } from './form-environment-variables.component';

@NgModule({
  declarations: [FormEnvironmentVariablesComponent],
  imports: [
    CommonModule,
    ReactiveFormsModule,
    KfFormModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
  ],
  exports: [FormEnvironmentVariablesComponent],
})
export class FormEnvironmentVariablesModule {}
