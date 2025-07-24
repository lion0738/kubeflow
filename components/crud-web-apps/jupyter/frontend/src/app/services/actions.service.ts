import { Injectable } from '@angular/core';
import {
  ConfirmDialogService,
  DIALOG_RESP,
  SnackBarConfig,
  SnackBarService,
  SnackType,
} from 'kubeflow';
import { getDeleteDialogConfig, getStopDialogConfig } from './config';
import { JWABackendService } from './backend.service';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root',
})
export class ActionsService {
  constructor(
    public backend: JWABackendService,
    public confirmDialog: ConfirmDialogService,
    private snackBar: SnackBarService,
  ) {}

  deleteNotebook(namespace: string, name: string): Observable<string> {
    return new Observable(subscriber => {
      const deleteDialogConfig = getDeleteDialogConfig(name);

      const ref = this.confirmDialog.open(name, deleteDialogConfig);
      const delSub = ref.componentInstance.applying$.subscribe(applying => {
        if (!applying) {
          return;
        }

        // Close the open dialog only if the DELETE request succeeded
        this.backend.deleteNotebook(namespace, name).subscribe({
          next: _ => {
            ref.close(DIALOG_RESP.ACCEPT);
            const object = `${namespace}/${name}`;
            const config: SnackBarConfig = {
              data: {
                msg: `${object}: Delete request was sent.`,
                snackType: SnackType.Info,
              },
              duration: 5000,
            };
            this.snackBar.open(config);
          },
          error: err => {
            const errorMsg = `Error ${err}`;
            deleteDialogConfig.error = errorMsg;
            ref.componentInstance.applying$.next(false);
            subscriber.next(`fail`);
          },
        });

        // DELETE request has succeeded
        ref.afterClosed().subscribe(result => {
          delSub.unsubscribe();
          subscriber.next(result);
          subscriber.complete();
        });
      });
    });
  }

  connectToNotebook(namespace: string, name: string): void {
    // Open new tab to work on the Notebook
    window.open(`/notebook/${namespace}/${name}/`);
  }

  downloadTextFile(filename: string, content: string): void {
    const element = document.createElement('a');
    element.href = 'data:application/octet-stream;charset=utf-8,' + encodeURIComponent(content);
    element.download = filename;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  }

  sshNotebook(namespace: string, name: string): void {
    this.backend.sshNotebook(namespace, name).subscribe({
      next: response => {
        const address = `SSH Address: knu-kubeflow.duckdns.org\nSSH Port: ${response[1]}\nID: ${response[2]}\nCommand: ssh -i ${name}_id_rsa -p ${response[1]} ${response[2]}@knu-kubeflow.duckdns.org`;
        this.downloadTextFile(`${name}_ssh_info.txt`, address);
        const privateKey = response[3] + '\n';
        this.downloadTextFile(`${name}_id_rsa`, privateKey);
      }
    });
  }

  portForwardNotebook(namespace: string, name: string): void {
    const portStr = window.prompt('Enter the port number to forward:', '8080');
    const port = Number(portStr);

    if (!port || isNaN(port)) {
      alert('Invalid port number.');
      return;
    }

    this.backend.portForwardNotebook(namespace, name, port).subscribe({
      next: response => {
        const address = `Service Address (Node IP): knu-kubeflow.duckdns.org\nTarget Port (inside Pod): ${response[1]}\nNodePort (external access): ${response[2]}`;
        this.downloadTextFile(`${name}_port_forward_info.txt`, address);
      }
    });
  }

  startNotebook(namespace: string, name: string): Observable<string> {
    return new Observable(subscriber => {
      this.backend.startNotebook(namespace, name).subscribe(response => {
        const config: SnackBarConfig = {
          data: {
            msg: $localize`Starting Notebook server '${name}'...`,
            snackType: SnackType.Info,
          },
        };
        this.snackBar.open(config);

        subscriber.next(response);
        subscriber.complete();
      });
    });
  }

  stopNotebook(namespace: string, name: string): Observable<string> {
    return new Observable(subscriber => {
      const stopDialogConfig = getStopDialogConfig(name);
      const ref = this.confirmDialog.open(name, stopDialogConfig);
      const stopSub = ref.componentInstance.applying$.subscribe(applying => {
        if (!applying) {
          return;
        }

        // Close the open dialog only if the request succeeded
        this.backend.stopNotebook(namespace, name).subscribe({
          next: _ => {
            ref.close(DIALOG_RESP.ACCEPT);
            const config: SnackBarConfig = {
              data: {
                msg: $localize`Stopping Notebook server '${name}'...`,
                snackType: SnackType.Info,
              },
            };
            this.snackBar.open(config);
          },
          error: err => {
            const errorMsg = `Error ${err}`;
            stopDialogConfig.error = errorMsg;
            ref.componentInstance.applying$.next(false);
            subscriber.next(`fail`);
          },
        });

        // request has succeeded
        ref.afterClosed().subscribe(result => {
          stopSub.unsubscribe();
          subscriber.next(result);
          subscriber.complete();
        });
      });
    });
  }

  deleteContainer(namespace: string, name: string): Observable<string> {
    return new Observable(subscriber => {
      const deleteDialogConfig = getDeleteDialogConfig(name);

      const ref = this.confirmDialog.open(name, deleteDialogConfig);
      const delSub = ref.componentInstance.applying$.subscribe(applying => {
        if (!applying) {
          return;
        }

        // Close the open dialog only if the DELETE request succeeded
        this.backend.deleteContainer(namespace, name).subscribe({
          next: _ => {
            ref.close(DIALOG_RESP.ACCEPT);
            const object = `${namespace}/${name}`;
            const config: SnackBarConfig = {
              data: {
                msg: `${object}: Delete request was sent.`,
                snackType: SnackType.Info,
              },
              duration: 5000,
            };
            this.snackBar.open(config);
          },
          error: err => {
            const errorMsg = `Error ${err}`;
            deleteDialogConfig.error = errorMsg;
            ref.componentInstance.applying$.next(false);
            subscriber.next(`fail`);
          },
        });

        // DELETE request has succeeded
        ref.afterClosed().subscribe(result => {
          delSub.unsubscribe();
          subscriber.next(result);
          subscriber.complete();
        });
      });
    });
  }

  startContainer(namespace: string, name: string): Observable<string> {
    return new Observable(subscriber => {
      this.backend.startContainer(namespace, name).subscribe(response => {
        const config: SnackBarConfig = {
          data: {
            msg: $localize`Starting Container '${name}'...`,
            snackType: SnackType.Info,
          },
        };
        this.snackBar.open(config);

        subscriber.next(response);
        subscriber.complete();
      });
    });
  }

  stopContainer(namespace: string, name: string): Observable<string> {
    return new Observable(subscriber => {
      const stopDialogConfig = getStopDialogConfig(name);
      const ref = this.confirmDialog.open(name, stopDialogConfig);
      const stopSub = ref.componentInstance.applying$.subscribe(applying => {
        if (!applying) {
          return;
        }

        // Close the open dialog only if the request succeeded
        this.backend.stopContainer(namespace, name).subscribe({
          next: _ => {
            ref.close(DIALOG_RESP.ACCEPT);
            const config: SnackBarConfig = {
              data: {
                msg: $localize`Stopping Container '${name}'...`,
                snackType: SnackType.Info,
              },
            };
            this.snackBar.open(config);
          },
          error: err => {
            const errorMsg = `Error ${err}`;
            stopDialogConfig.error = errorMsg;
            ref.componentInstance.applying$.next(false);
            subscriber.next(`fail`);
          },
        });

        // request has succeeded
        ref.afterClosed().subscribe(result => {
          stopSub.unsubscribe();
          subscriber.next(result);
          subscriber.complete();
        });
      });
    });
  }
}
