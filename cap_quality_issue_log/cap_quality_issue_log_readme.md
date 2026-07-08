# Quality Issue Log By Captivea

## Version
Odoo 18.0

## Dependencies
1. hr
2. contacts
3. base_automation
4. analytic
5. hr_gamification
6. hr_holidays
7. cap_partner
8. ksc_project_extended
9. cap_project_progress_report

## Description
In this module, we create quality issue logs based on conditions for our employees and manage the global quality score
for employees on a monthly basis.

## Features
Here are the main features of this module:
- **Quality Issue Types:**
  Here, we have quality issue type and based on this quality issue type quality issue log is raised.
- **Quality Issue Logs:**
  The quality issue log is a type of message in object form that shows quality issues for employees.
- **Global Quality Score:**
  The global quality score is calculated based on the quality issue logs generated for employees and set on goal and
  employees form, updated monthly. Each quality issue log impacts the score, and this field is used to calculate both
  the global quality score and the score for each type of quality issue.
- **Ask For Review On Quality Issue Log:**
  On the quality issue log form, there is an 'Ask for Review' button. If a quality issue log is created and the employee
  has a valid reason, they can request a review of the quality issue log. If the employee provides a valid reason, their
  manager or another authorized user can disable the quality issue log. The impact of a quality issue log is only
  counted if the log is not disabled
- **Exclude From Quality Control Field:**
  If the boolean field 'exclude from quality control' is true for an employee, then the global quality score for that
  employee is not calculated.

## Author & Maintainer
CAPTIVEA INDIA
