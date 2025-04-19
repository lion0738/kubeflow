import { Component, Input } from '@angular/core';
import { FormGroup } from '@angular/forms';

@Component({
  selector: 'app-form-command',
  templateUrl: './form-command.component.html',
})
export class FormCommandComponent {
  @Input() parentForm: FormGroup;
}
