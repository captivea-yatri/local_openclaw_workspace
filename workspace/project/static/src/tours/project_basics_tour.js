// -*- coding: utf-8 -*-
/**
 * UI tour for the "Project Basics" walkthrough.
 * This tour guides a user through the main Project tab, explains the
 * status legend, filters, group‑by, favorites, overview and edit actions.
 */
odoo.define('project.tour_project_basics', function (require) {
    "use strict";

    var tour = require('web_tour.tour');

    // Register the tour. It runs in test mode and starts on the Projects list view.
    tour.register('project_basics_tour', {
        test: true,
        // The URL that shows the list of projects.
        url: '/web?#action=project.project_action',
    }, [
        {
            // Step 1 – Open the Projects app if we are not already there.
            content: "Welcome to the Projects module!",
            trigger: '.o_app[data-menu-xmlid="project.menu_project"]',
            run: 'click',
        },
        {
            // Step 2 – Explain the project list heading.
            content: "Here you see the list of all client projects.",
            trigger: '.o_content .o_list_view',
            timeout: 2000,
        },
        {
            // Step 3 – Show the favourite star next to a project name.
            content: "Click the empty grey star to add a project to \"My Favorites\".",
            // The star icon has class o_favorite_star on each row.
            trigger: '.o_list_view tr:first .o_favorite_star',
            run: 'click',
        },
        {
            // Step 4 – Open the favourite filter.
            content: "Now open the \"My Favorites\" filter to see only favourited projects.",
            trigger: '.o_searchview .dropdown-toggle:contains("Filters")',
            run: 'click',
        },
        {
            content: "Select the \"My Favorites\" filter.",
            trigger: '.o_searchview .dropdown-menu a:contains("My Favorites")',
            run: 'click',
        },
        {
            // Step 5 – Explain the status column and its colour legend.
            content: "The status column uses colours to indicate the project phase.\n\n" +
                     "• Empty – Brand‑new project\n" +
                     "• Analysis – Design phase (client not using Odoo)\n" +
                     "• Pre‑Live Configuration – Implementation phase\n" +
                     "• Live (On‑going customization) – Client using Odoo\n" +
                     "• Live (Support) – Project delivered, support only\n" +
                     "• On Hold (Not Live) / On Hold (Live) – Project paused",
            trigger: '.o_list_view th:contains("Status")',
        },
        {
            // Step 6 – Show the Filters button.
            content: "Use Filters to quickly find projects by manager, customer or status.",
            trigger: '.o_searchview .dropdown-toggle:contains("Filters")',
            run: 'click',
        },
        {
            content: "Try the \"My Projects\" filter – it shows projects where you are the PM.",
            trigger: '.o_searchview .dropdown-menu a:contains("My Projects")',
            run: 'click',
        },
        {
            // Step 7 – Show the Group By button.
            content: "Group By lets you group projects by manager, customer, go‑live period, etc.",
            trigger: '.o_searchview .dropdown-toggle:contains("Group By")',
            run: 'click',
        },
        {
            content: "Select a grouping, e.g., \"Project Manager\".",
            trigger: '.o_searchview .dropdown-menu a:contains("Project Manager")',
            run: 'click',
        },
        {
            // Step 8 – Open a project’s Overview.
            content: "Open a project’s Overview to see hours, sales orders and quick timesheet access.",
            trigger: '.o_list_view tr:first .o_field_widget[name="name"] a',
            run: 'click',
        },
        {
            // Step 9 – Click the Overview link (bottom‑right of the card).
            content: "Click the \"Overview\" link to open the project overview page.",
            // In the kanban view the button has .o_project_overview.
            trigger: '.o_project_overview',
            run: 'click',
        },
        {
            // Step 10 – Inside Overview, show the Settings (three‑dot) menu.
            content: "From the Overview you can reach Settings (three‑dot menu) to edit the project.",
            trigger: '.o_project_overview .dropdown-toggle',
            run: 'click',
        },
        {
            content: "Click \"Edit\" to open the project form.",
            trigger: '.dropdown-menu a:contains("Edit")',
            run: 'click',
        },
        {
            // Step 11 – Highlight the Status field in the form view.
            content: "Here you can change the project status to any of the values described earlier.",
            trigger: '.o_form_view .o_field_widget[name="status"]',
        },
        {
            // Step 12 – Demonstrate sharing the project.
            content: "Click the \"Share editable\" button to give portal users edit access.",
            trigger: '.o_form_view button:contains("Share editable")',
            run: 'click',
        },
        {
            // Step 13 – End of the tour.
            content: "Great! You now know the basics of navigating the Projects module.",
            trigger: 'body',
            timeout: 2000,
        },
    ]);
});
