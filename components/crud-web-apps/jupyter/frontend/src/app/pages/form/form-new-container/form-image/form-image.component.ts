import { Component, OnInit, Input, OnDestroy } from '@angular/core';
import { FormGroup, Validators } from '@angular/forms';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-form-image',
  templateUrl: './form-image.component.html',
  styleUrls: ['./form-image.component.scss'],
})
export class FormImageComponent implements OnInit, OnDestroy {
  @Input() parentForm: FormGroup;

  subs = new Subscription();

  ngOnInit() {
    // 무조건 customImage 입력 받기
    const customImageCtrl = this.parentForm.get('customImage');
    if (customImageCtrl) {
      customImageCtrl.setValidators(Validators.required);
      customImageCtrl.updateValueAndValidity();
    }
  }

  ngOnDestroy() {
    this.subs.unsubscribe();
  }
}
