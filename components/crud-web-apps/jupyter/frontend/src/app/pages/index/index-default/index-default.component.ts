import { Component, OnInit, OnDestroy } from '@angular/core';
import { environment } from '@app/environment';
import {
  NamespaceService,
  ActionEvent,
  STATUS_TYPE,
  ConfirmDialogService,
  SnackBarService,
  DIALOG_RESP,
  SnackType,
  ToolbarButton,
  PollerService,
  DashboardState,
  SnackBarConfig,
} from 'kubeflow';
import { JWABackendService } from 'src/app/services/backend.service';
import { Subscription } from 'rxjs';
import { defaultConfig } from './config';
import { NotebookResponseObject, NotebookProcessedObject } from 'src/app/types';
import { Router } from '@angular/router';
import { ActionsService } from 'src/app/services/actions.service';

@Component({
  selector: 'app-index-default',
  templateUrl: './index-default.component.html',
  styleUrls: ['./index-default.component.scss'],
})
export class IndexDefaultComponent implements OnInit, OnDestroy {
  env = environment;

  nsSub = new Subscription();
  pollSub = new Subscription();

  currNamespace: string | string[];
  config = defaultConfig;
  processedData: NotebookProcessedObject[] = [];
  dashboardDisconnectedState = DashboardState.Disconnected;
  private connectLoadingState = new Map<string, boolean>();

  private newContainerButton = new ToolbarButton({
    text: $localize`New Container`,
    icon: 'add',
    stroked: true,
    fn: () => {
      this.router.navigate(['/new-container']);
    },
  });

  private newNotebookButton = new ToolbarButton({
    text: $localize`New Notebook`,
    icon: 'add',
    stroked: true,
    fn: () => {
      this.router.navigate(['/new']);
    },
  });

  buttons: ToolbarButton[] = [this.newContainerButton, this.newNotebookButton];

  constructor(
    public ns: NamespaceService,
    public backend: JWABackendService,
    public confirmDialog: ConfirmDialogService,
    public snackBar: SnackBarService,
    public router: Router,
    public poller: PollerService,
    public actions: ActionsService,
  ) {}

  ngOnInit(): void {
    // Reset the poller whenever the selected namespace changes
    this.nsSub = this.ns.getSelectedNamespace2().subscribe(ns => {
      this.currNamespace = ns;
      this.poll(ns);
      this.newContainerButton.namespaceChanged(ns, $localize`Container`);
      this.newNotebookButton.namespaceChanged(ns, $localize`Notebook`);
    });
  }

  ngOnDestroy() {
    this.nsSub.unsubscribe();
    this.pollSub.unsubscribe();
  }

  public poll(ns: string | string[]) {
    this.pollSub.unsubscribe();
    this.processedData = [];

    const request = this.backend.getNotebooks(ns);

    this.pollSub = this.poller.exponential(request).subscribe(notebooks => {
      this.processedData = this.processIncomingData(notebooks);
    });
  }

  // Event handling functions
  reactToAction(a: ActionEvent) {
    switch (a.action) {
      case 'delete':
        this.deleteNotebookClicked(a.data);
        break;
      case 'connect':
        this.connectClicked(a.data);
        break;
      case 'ssh':
        this.sshClicked(a.data);
        break;
      case 'port-forward':
        this.portForwardClicked(a.data);
        break;
      case 'start-stop':
        this.startStopClicked(a.data);
        break;
      case 'name:link':
        if (a.data.status.phase === STATUS_TYPE.TERMINATING) {
          a.event.stopPropagation();
          a.event.preventDefault();
          const config: SnackBarConfig = {
            data: {
              msg: 'Notebook is being deleted, cannot show details.',
              snackType: SnackType.Info,
            },
            duration: 4000,
          };
          this.snackBar.open(config);
          return;
        }
        break;
    }
  }

  deleteNotebookClicked(notebook: NotebookProcessedObject) {
    const isContainer = notebook.serverType === 'container';

    const deleteAction = isContainer
      ? this.actions.deleteContainer(notebook.namespace, notebook.name)
      : this.actions.deleteNotebook(notebook.namespace, notebook.name);
  
    deleteAction.subscribe(result => {
      if (result !== DIALOG_RESP.ACCEPT) return;
  
      notebook.status.phase = STATUS_TYPE.TERMINATING;
      notebook.status.message = isContainer
        ? 'Preparing to delete the Container.'
        : 'Preparing to delete the Notebook.';
      this.updateNotebookFields(notebook);
    });
  }

  public connectClicked(notebook: NotebookProcessedObject) {
    if (notebook.serverType === 'container') {
      const command = window.prompt(
        'Enter the command to run in the container',
        'bash',
      );

      if (command === null) {
        return;
      }

      this.setConnectLoadingState(notebook, true);
      this.updateNotebookFields(notebook);

      this.actions
        .connectToContainer(notebook.namespace, notebook.name, command)
        .subscribe({
          next: () => {
            this.setConnectLoadingState(notebook, false);
            this.updateNotebookFields(notebook);
          },
          error: err => {
            const message =
              typeof err === 'string'
                ? err
                : err?.message || 'Failed to open CloudShell session.';
            const config: SnackBarConfig = {
              data: {
                msg: message,
                snackType: SnackType.Error,
              },
              duration: 5000,
            };
            this.snackBar.open(config);

            this.setConnectLoadingState(notebook, false);
            this.updateNotebookFields(notebook);
          },
        });
      return;
    }

    this.actions.connectToNotebook(notebook.namespace, notebook.name);
  }

  public sshClicked(notebook: NotebookProcessedObject) {
    this.actions.sshNotebook(notebook.namespace, notebook.name);
  }

  public portForwardClicked(notebook: NotebookProcessedObject) {
    this.actions.portForwardNotebook(notebook.namespace, notebook.name);
  }

  public startStopClicked(notebook: NotebookProcessedObject) {
    if (notebook.status.phase === STATUS_TYPE.STOPPED) {
      this.startNotebook(notebook);
    } else {
      this.stopNotebook(notebook);
    }
  }

  public startNotebook(notebook: NotebookProcessedObject) {
    const isContainer = notebook.serverType === 'container';

    const startAction = isContainer
      ? this.actions.startContainer(notebook.namespace, notebook.name)
      : this.actions.startNotebook(notebook.namespace, notebook.name);
  
    startAction.subscribe(result => {
      notebook.status.phase = STATUS_TYPE.WAITING;
      notebook.status.message = isContainer
        ? 'Starting the Container.'
        : 'Starting the Notebook Server.';
      this.updateNotebookFields(notebook);
    });
  }

  public stopNotebook(notebook: NotebookProcessedObject) {
    const isContainer = notebook.serverType === 'container';

    const stopAction = isContainer
      ? this.actions.stopContainer(notebook.namespace, notebook.name)
      : this.actions.stopNotebook(notebook.namespace, notebook.name);
  
    stopAction.subscribe(result => {
      if (result !== DIALOG_RESP.ACCEPT) return;
  
      notebook.status.phase = STATUS_TYPE.WAITING;
      notebook.status.message = isContainer
        ? 'Preparing to stop the Container.'
        : 'Preparing to stop the Notebook Server.';
      this.updateNotebookFields(notebook);
    });
  }

  // Data processing functions
  updateNotebookFields(notebook: NotebookProcessedObject) {
    this.applyConnectLoadingState(notebook);
    notebook.deleteAction = this.processDeletionActionStatus(notebook);
    notebook.connectAction = this.processConnectActionStatus(notebook);
    notebook.sshAction = this.processSshActionStatus(notebook);
    notebook.portForwardAction = this.processPortForwardActionStatus(notebook);
    notebook.startStopAction = this.processStartStopActionStatus(notebook);
    let url = null;
    if (notebook.serverType === 'container') {
      url = `/container/details/${notebook.namespace}/${notebook.name}`;
    } else {
      url = `/notebook/details/${notebook.namespace}/${notebook.name}`;
    }

    notebook.link = {
      text: notebook.name,
      url: url,
    };
  }

  private applyConnectLoadingState(notebook: NotebookProcessedObject) {
    const key = this.getNotebookKey(notebook);
    notebook.connectLoading = this.connectLoadingState.get(key) ?? false;
  }

  private setConnectLoadingState(
    notebook: NotebookProcessedObject,
    loading: boolean,
  ) {
    const key = this.getNotebookKey(notebook);
    if (loading) {
      this.connectLoadingState.set(key, true);
    } else {
      this.connectLoadingState.delete(key);
    }
    notebook.connectLoading = loading;
  }

  private getNotebookKey(notebook: NotebookProcessedObject): string {
    return `${notebook.namespace}/${notebook.name}`;
  }

  processIncomingData(notebooks: NotebookResponseObject[]) {
    const notebooksCopy = JSON.parse(
      JSON.stringify(notebooks),
    ) as NotebookProcessedObject[];

    for (const nb of notebooksCopy) {
      this.updateNotebookFields(nb);
    }
    return notebooksCopy;
  }

  // Action handling functions
  processDeletionActionStatus(notebook: NotebookProcessedObject) {
    if (notebook.status.phase !== STATUS_TYPE.TERMINATING) {
      return STATUS_TYPE.READY;
    }

    return STATUS_TYPE.TERMINATING;
  }

  processStartStopActionStatus(notebook: NotebookProcessedObject) {
    // Stop button
    if (notebook.status.phase === STATUS_TYPE.READY) {
      return STATUS_TYPE.UNINITIALIZED;
    }

    // Start button
    if (notebook.status.phase === STATUS_TYPE.STOPPED) {
      return STATUS_TYPE.READY;
    }

    // If it is terminating, then the action should be disabled
    if (notebook.status.phase === STATUS_TYPE.TERMINATING) {
      return STATUS_TYPE.UNAVAILABLE;
    }

    // If the Notebook is not Terminating, then always allow the stop action
    return STATUS_TYPE.UNINITIALIZED;
  }

  processConnectActionStatus(notebook: NotebookProcessedObject) {
    if (notebook.connectLoading) {
      return STATUS_TYPE.UNAVAILABLE;
    }

    if (notebook.status.phase !== STATUS_TYPE.READY) {
      return STATUS_TYPE.UNAVAILABLE;
    }

    return STATUS_TYPE.READY;
  }

  processSshActionStatus(notebook: NotebookProcessedObject) {
    if (notebook.status.phase !== STATUS_TYPE.READY || notebook.serverType === 'container') {
      return STATUS_TYPE.UNAVAILABLE;
    }

    return STATUS_TYPE.READY;
  }

  processPortForwardActionStatus(notebook: NotebookProcessedObject) {
    if (notebook.status.phase !== STATUS_TYPE.READY) {
      return STATUS_TYPE.UNAVAILABLE;
    }

    return STATUS_TYPE.READY;
  }

  public notebookTrackByFn(index: number, notebook: NotebookProcessedObject) {
    return `${notebook.name}/${notebook.image}`;
  }
}
