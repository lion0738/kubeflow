import { Component, OnInit, OnDestroy } from '@angular/core';
import { FormGroup } from '@angular/forms';
import { Config, NotebookFormObject } from 'src/app/types';
import { Subscription } from 'rxjs';
import {
  NamespaceService,
  SnackBarConfig,
  SnackBarService,
  SnackType,
} from 'kubeflow';
import { Router } from '@angular/router';
import { getFormDefaults, initFormControls } from './utils';
import { JWABackendService } from 'src/app/services/backend.service';

@Component({
  selector: 'app-form-new-container',
  templateUrl: './form-new-container.component.html',
  styleUrls: ['./form-new-container.component.scss'],
})
export class FormNewContainerComponent implements OnInit, OnDestroy {
  currNamespace = '';
  formCtrl: FormGroup;
  config: Config;

  defaultStorageclass = false;

  subscriptions = new Subscription();

  constructor(
    public namespaceService: NamespaceService,
    public backend: JWABackendService,
    public router: Router,
    public popup: SnackBarService,
  ) {}

  ngOnInit(): void {
    // Initialize the form control
    this.formCtrl = this.getFormDefaults();

    // Update the form Values from the default ones
    this.backend.getConfig().subscribe(config => {
      if (Object.keys(config).length === 0) {
        // Don't fire on empty config
        return;
      }

      this.config = config;
      this.initFormControls(this.formCtrl, config);
    });

    // Keep track of the selected namespace
    this.subscriptions.add(
      this.namespaceService.getSelectedNamespace2().subscribe(namespace => {
        if (Array.isArray(namespace)) {
          this.goToNotebooks();
        } else {
          this.currNamespace = namespace;
          this.formCtrl.controls.namespace.setValue(this.currNamespace);
        }
      }),
    );

    // Check if a default StorageClass is set
    this.backend.getDefaultStorageClass().subscribe(defaultClass => {
      if (defaultClass.length === 0) {
        this.defaultStorageclass = false;
        const configWarning: SnackBarConfig = {
          data: {
            msg: $localize`No default Storage Class is set. Can't create new Disks for the new Container. Please use an Existing Disk.`,
            snackType: SnackType.Warning,
          },
          duration: 0,
        };
        this.popup.open(configWarning);
      } else {
        this.defaultStorageclass = true;
      }
    });
  }

  ngOnDestroy() {
    // Unsubscriptions
    this.subscriptions.unsubscribe();
  }

  // Functions for handling the Form Group of the entire Form
  getFormDefaults() {
    return getFormDefaults();
  }

  initFormControls(formCtrl: FormGroup, config: Config) {
    initFormControls(formCtrl, config);
  }

  // Form Actions
  getSubmitContainer(): any {
    const notebookCopy = this.formCtrl.value as NotebookFormObject;
    const notebook = JSON.parse(JSON.stringify(notebookCopy));

    // Use custom image
    notebook.image = notebook.customImage?.trim();

    // Ensure CPU input is a string
    if (typeof notebook.cpu === 'number') {
      notebook.cpu = notebook.cpu.toString();
    }

    // Ensure GPU input is a string
    if (notebook.gpus && typeof notebook.gpus.num === 'number') {
      notebook.gpus.num = notebook.gpus.num.toString();
    }

    // Remove cpuLimit from request if null
    if (notebook.cpuLimit == null) {
      delete notebook.cpuLimit;
      // Ensure CPU Limit input is a string
    } else if (typeof notebook.cpuLimit === 'number') {
      notebook.cpuLimit = notebook.cpuLimit.toString();
    }

    // Add Gi to all sizes
    if (notebook.memory) {
      notebook.memory = notebook.memory.toString() + 'Gi';
    }

    for (const vol of notebook.datavols) {
      if (vol.size) {
        vol.size = vol.size + 'Gi';
      }
    }

    // command 필드 수동으로 붙이기
    const command = notebook['command']
      ? notebook['command']
      : '/bin/bash -c sleep infinity';

    // Prepare environment variables
    const envs = notebook.envs
      ? notebook.envs
      : [];

    // 백엔드에 전송할 필드만 추려서 리턴
    const payload = {
      name: notebook.name,
      namespace: notebook.namespace,
      image: notebook.image,
      command: command,
      ports: [],
      resources: {
        cpu: notebook.cpu,
        memory: notebook.memory,
        ...(notebook.gpus?.num !== 'none' ? { 'nvidia.com/gpu': notebook.gpus.num } : {})
      },
      datavols: notebook.datavols,
      envs: envs,
    };

    return payload;
  }

  // Set the tooltip text based on form's validity
  setTooltipText(form: FormGroup): string {
    let text: string;
    if (!form.get('name').valid) {
      text = 'No value of the Notebook name was provided';
    } else if (!form.controls.valid) {
      text = 'The form contains invalid fields';
    }
    return text;
  }

  onSubmit() {
    const configInfo: SnackBarConfig = {
      data: {
        msg: 'Submitting new Container...',
        snackType: SnackType.Info,
      },
    };
    this.popup.open(configInfo);

    const container = this.getSubmitContainer();
    this.backend.createContainer(container).subscribe(() => {
      this.popup.close();
      const configSuccess: SnackBarConfig = {
        data: {
          msg: 'Container created successfully.',
          snackType: SnackType.Success,
        },
      };
      this.popup.open(configSuccess);
      this.goToNotebooks(); // 또는 목록 새로고침
    });
  }

  onCancel() {
    this.goToNotebooks();
  }

  goToNotebooks() {
    this.router.navigate(['/']);
  }
}
