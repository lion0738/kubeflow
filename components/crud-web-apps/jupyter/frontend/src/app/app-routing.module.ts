import { NgModule } from '@angular/core';
import { Routes, RouterModule } from '@angular/router';

import { FormNewComponent } from './pages/form/form-new/form-new.component';
import { FormNewContainerComponent } from './pages/form/form-new-container/form-new-container.component';
import { IndexDefaultComponent } from './pages/index/index-default/index-default.component';
import { NotebookPageComponent } from './pages/notebook-page/notebook-page.component';

const routes: Routes = [
  { path: '', component: IndexDefaultComponent },
  { path: 'new', component: FormNewComponent },
  { path: 'new-container', component: FormNewContainerComponent },
  {
    path: 'notebook/details/:namespace/:notebookName',
    component: NotebookPageComponent,
    data: { resourceType: 'notebook' },
  },
  {
    path: 'container/details/:namespace/:name',
    component: NotebookPageComponent,
    data: { resourceType: 'container' },
  },
];

@NgModule({
  imports: [RouterModule.forRoot(routes, { relativeLinkResolution: 'legacy' })],
  exports: [RouterModule],
})
export class AppRoutingModule {}
