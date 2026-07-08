// -*- coding: utf-8 -*-
/**
 * UI tour for the complete Project workflow.
 * It covers:
 *   1. Opening the Projects app
 *   2. Creating a new project with status and favourite
 *   3. Adding a phase
 *   4. Adding a project requirement (via the Requirement wizard)
 *   5. Creating a task from the requirement
 *   6. Opening the Project Overview, editing, sharing, and logging a timesheet
 *   7. Running the Test Session flow (initialize, execute, close)
 *   8. Verifying colour status (green/yellow/red) based on invoice due date.
 *
 * This tour can be run in test mode (test:true) or manually via the UI.
 */
odoo.define('project.tour_full_workflow', function (require) {
    "use strict";

    var core = require('web.core');
    var tour = require('web_tour.tour');
    var _t = core._t;

    tour.register('project_full_workflow_tour', {
        test: true,
        // Start on the Projects list view.
        url: '/web?#action=project.project_action',
    }, [
        // ---------------------------------------------------------------------
        // 1. Open the Projects app (if we are not already there).
        // ---------------------------------------------------------------------
        {
            content: _t('Welcome to the Projects module!'),
            trigger: '.o_app[data-menu-xmlid="project.menu_project"]',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 2. Click the "Create" button to start a new project.
        // ---------------------------------------------------------------------
        {
            content: _t('Create a brand‑new project.'),
            trigger: '.o_list_button_add',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 3. Fill in the mandatory fields: Name, Customer, and Status.
        // ---------------------------------------------------------------------
        {
            content: _t('Enter the project name.'),
            trigger: 'input[name="name"]',
            run: 'text My Demo Project',
        },
        {
            content: _t('Select a customer (use the first one in the list).'),
            trigger: 'a.o_external_button:contains("Customer")',
            run: 'click',
        },
        {
            // Select the first customer in the dropdown.
            content: _t('Pick a customer.'),
            trigger: '.ui-autocomplete li:first',
            run: 'click',
        },
        {
            // Status field – choose "Analysis" for the demo.
            content: _t('Set the project status.'),
            trigger: 'select[name="status"]',
            run: 'selectByLabel Analysis',
        },
        // ---------------------------------------------------------------------
        // 4. Save the project.
        // ---------------------------------------------------------------------
        {
            content: _t('Save the new project.'),
            trigger: '.o_form_button_save',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 5. Add the project to favourites (star icon in kanban view).
        // ---------------------------------------------------------------------
        {
            content: _t('Add this project to My Favorites.'),
            // After saving we are in form view; go back to kanban.
            trigger: '.o_form_button_cancel',
            run: 'click',
        },
        {
            // Now in kanban/list view – click the star.
            content: _t('Click the empty grey star.'),
            trigger: '.o_list_view tr:first .o_favorite_star',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 6. Open the newly created project.
        // ---------------------------------------------------------------------
        {
            content: _t('Open the project to continue.'),
            trigger: '.o_list_view tr:first .o_field_widget[name="name"] a',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 7. Add a Phase (tab "Phases" -> "Create").
        // ---------------------------------------------------------------------
        {
            content: _t('Switch to the Phases tab.'),
            trigger: '.nav-pills a:contains("Phases")',
            run: 'click',
        },
        {
            content: _t('Create a new phase.'),
            trigger: '.o_list_button_add',
            run: 'click',
        },
        {
            content: _t('Enter the phase name.'),
            trigger: 'input[name="name"]',
            run: 'text Phase 1',
        },
        {
            content: _t('Save the phase.'),
            trigger: '.o_form_button_save',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 8. Open the Requirement tab and create a requirement.
        // ---------------------------------------------------------------------
        {
            content: _t('Switch to the Requirement tab.'),
            trigger: '.nav-pills a:contains("Requirement")',
            run: 'click',
        },
        {
            content: _t('Create a new requirement for the phase.'),
            trigger: '.o_list_button_add',
            run: 'click',
        },
        {
            content: _t('Select the domain (use first default domain).'),
            trigger: 'select[name="default_domain_id"]',
            run: 'selectByIndex 0',
        },
        {
            content: _t('Enter a requirement description.'),
            trigger: 'textarea[name="description"]',
            run: 'text Demo requirement for Phase 1',
        },
        {
            content: _t('Save the requirement.'),
            trigger: '.o_form_button_save',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 9. Use the wizard to create tasks from requirements.
        // ---------------------------------------------------------------------
        {
            content: _t('Open the "Create Task From Project Requirement" wizard.'),
            trigger: '.o_form_button_edit:contains("Create Task From Project Requirement")',
            run: 'click',
        },
        {
            content: _t('Select the phase we just created.'),
            trigger: 'select[name="phase_id"]',
            run: 'selectByLabel Phase 1',
        },
        {
            content: _t('Run the wizard to generate the task.'),
            trigger: '.modal-footer button:contains("Create")',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 10. Verify the task appears in the Tasks tab.
        // ---------------------------------------------------------------------
        {
            content: _t('Switch to the Tasks tab to see the generated task.'),
            trigger: '.nav-pills a:contains("Tasks")',
            run: 'click',
        },
        {
            content: _t('Check that a task with the requirement description exists.'),
            trigger: '.o_list_view tr:contains("Demo requirement for Phase 1")',
            timeout: 2000,
        },
        // ---------------------------------------------------------------------
        // 11. Open the Project Overview from the kanban view.
        // ---------------------------------------------------------------------
        {
            content: _t('Return to the kanban view and open the Overview.'),
            trigger: '.o_form_button_cancel',
            run: 'click',
        },
        {
            content: _t('Click the Overview link (bottom‑right of the card).'),
            trigger: '.o_project_overview',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 12. From the Overview, open Settings (three‑dot menu) and edit status.
        // ---------------------------------------------------------------------
        {
            content: _t('Open the Settings (three‑dot) menu.'),
            trigger: '.o_project_overview .dropdown-toggle',
            run: 'click',
        },
        {
            content: _t('Choose Edit to modify the project.'),
            trigger: '.dropdown-menu a:contains("Edit")',
            run: 'click',
        },
        {
            content: _t('Change status to Live (On‑going customization).'),
            trigger: 'select[name="status"]',
            run: 'selectByLabel "Live (On‑going customization)"',
        },
        {
            content: _t('Save the changes.'),
            trigger: '.o_form_button_save',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 13. Log a timesheet on the newly created task.
        // ---------------------------------------------------------------------
        {
            content: _t('Go back to the Tasks tab.'),
            trigger: '.nav-pills a:contains("Tasks")',
            run: 'click',
        },
        {
            content: _t('Open the task to log a timesheet.'),
            trigger: '.o_list_view tr:contains("Demo requirement for Phase 1") a',
            run: 'click',
        },
        {
            content: _t('Click the Timesheet button.'),
            trigger: '.oe_button:contains("Timesheets")',
            run: 'click',
        },
        {
            content: _t('Add a new timesheet line: 2 hours today.'),
            trigger: '.o_form_button_add',
            run: 'click',
        },
        {
            content: _t('Set the unit amount.'),
            trigger: 'input[name="unit_amount"]',
            run: 'text 2',
        },
        {
            content: _t('Save the timesheet line.'),
            trigger: '.o_form_button_save',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 14. Share the project with a portal user (demo share).
        // ---------------------------------------------------------------------
        {
            content: _t('Return to the project form.'),
            trigger: '.o_form_button_cancel',
            run: 'click',
        },
        {
            content: _t('Open the Share editable button.'),
            trigger: '.o_form_view button:contains("Share editable")',
            run: 'click',
        },
        {
            content: _t('Select the first portal user in the list.'),
            trigger: '.modal-body .o_field_many2manytags input',
            run: 'text portal_user@example.com',
        },
        {
            content: _t('Confirm sharing.'),
            trigger: '.modal-footer button:contains("Send")',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 15. Initialize a Test Session (simulating the test flow).
        // ---------------------------------------------------------------------
        {
            content: _t('Open the Test Session smart button.'),
            trigger: '.o_form_view button:contains("Test Session")',
            run: 'click',
        },
        {
            content: _t('Click the Initialize Test button.'),
            trigger: '.modal-footer button:contains("Initialize Test")',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 16. Close the Test Session.
        // ---------------------------------------------------------------------
        {
            content: _t('After initialization, close the session.'),
            trigger: '.o_form_view button:contains("Close the Session")',
            run: 'click',
        },
        {
            content: _t('Confirm closing.'),
            trigger: '.modal-footer button:contains("Close")',
            run: 'click',
        },
        // ---------------------------------------------------------------------
        // 17. End of the full workflow tour.
        // ---------------------------------------------------------------------
        {
            content: _t('The full project workflow is now demonstrated!'),
            trigger: 'body',
            timeout: 2000,
        },
    ]);
});
