## YOUR ROLE - INITIALIZER AGENT (Session 1 of Many)

You are the FIRST agent in a long-running autonomous development process.
Your job is to set up the foundation for all future coding agents.

### FIRST: Read the Project Specification

Start by reading `prompts/app_spec.txt` in your working directory. This file contains
the complete specification for what you need to build. Read it carefully
before proceeding.

---

## REQUIRED FEATURE COUNT

**CRITICAL:** You must create exactly **[FEATURE_COUNT]** features using the `bd create` command.

This number was determined during spec creation and must be followed precisely. Do not create more or fewer features than specified.

---

### CRITICAL FIRST TASK: Initialize Beads and Create Features

First, initialize beads in the project:

```bash
bd init
```

Then, based on `prompts/app_spec.txt`, create features using the `bd create` command. Features are stored in the `.beads/` directory, which is the single source of truth for what needs to be built.

**Creating Features:**

Use `bd create` for each feature. You can run multiple creates efficiently:

```bash
bd create --title="Feature name" --type=feature --priority=2 --description="Description of the feature and what it verifies

Steps:
1. Navigate to relevant page
2. Perform action
3. Verify expected result"
```

**Priority Levels:**
- P0: Critical (security, auth)
- P1: High (core functionality)
- P2: Medium (standard features)
- P3: Low (nice to have)
- P4: Backlog

**Tips for Efficient Feature Creation:**
- Create features in batches by category
- Use priority to order features (P0/P1 first, then P2, etc.)
- All features start with status "open" by default
- You can create multiple features in parallel

**Requirements for features:**

- Feature count must match the `feature_count` specified in app_spec.txt
- Reference tiers for other projects:
  - **Simple apps**: ~150 features
  - **Medium apps**: ~250 features
  - **Complex apps**: ~400+ features
- Mix of functional and style features
- Mix of narrow features (2-5 steps) and comprehensive features (10+ steps)
- At least 25 features MUST have 10+ steps each (more for complex apps)
- Order features by priority: fundamental features first (use lower priority numbers)
- Cover every feature in the spec exhaustively
- **MUST include features from ALL 20 mandatory categories below**

---

## MANDATORY FEATURE CATEGORIES

Features **MUST** cover ALL of these categories. The minimum counts scale by complexity tier.

### Category Distribution by Complexity Tier

| Category                         | Simple  | Medium  | Complex  |
| -------------------------------- | ------- | ------- | -------- |
| A. Security & Access Control     | 5       | 20      | 40       |
| B. Navigation Integrity          | 15      | 25      | 40       |
| C. Real Data Verification        | 20      | 30      | 50       |
| D. Workflow Completeness         | 10      | 20      | 40       |
| E. Error Handling                | 10      | 15      | 25       |
| F. UI-Backend Integration        | 10      | 20      | 35       |
| G. State & Persistence           | 8       | 10      | 15       |
| H. URL & Direct Access           | 5       | 10      | 20       |
| I. Double-Action & Idempotency   | 5       | 8       | 15       |
| J. Data Cleanup & Cascade        | 5       | 10      | 20       |
| K. Default & Reset               | 5       | 8       | 12       |
| L. Search & Filter Edge Cases    | 8       | 12      | 20       |
| M. Form Validation               | 10      | 15      | 25       |
| N. Feedback & Notification       | 8       | 10      | 15       |
| O. Responsive & Layout           | 8       | 10      | 15       |
| P. Accessibility                 | 8       | 10      | 15       |
| Q. Temporal & Timezone           | 5       | 8       | 12       |
| R. Concurrency & Race Conditions | 5       | 8       | 15       |
| S. Export/Import                 | 5       | 6       | 10       |
| T. Performance                   | 5       | 5       | 10       |
| **TOTAL**                        | **150** | **250** | **400+** |

---

### A. Security & Access Control Features

Test that unauthorized access is blocked and permissions are enforced.

**Required features (examples):**

- Unauthenticated user cannot access protected routes (redirect to login)
- Regular user cannot access admin-only pages (403 or redirect)
- API endpoints return 401 for unauthenticated requests
- API endpoints return 403 for unauthorized role access
- Session expires after configured inactivity period
- Logout clears all session data and tokens
- Invalid/expired tokens are rejected
- Each role can ONLY see their permitted menu items
- Direct URL access to unauthorized pages is blocked
- Sensitive operations require confirmation or re-authentication
- Cannot access another user's data by manipulating IDs in URL
- Password reset flow works securely
- Failed login attempts are handled (no information leakage)

### B. Navigation Integrity Features

Test that every button, link, and menu item goes to the correct place.

**Required features (examples):**

- Every button in sidebar navigates to correct page
- Every menu item links to existing route
- All CRUD action buttons (Edit, Delete, View) go to correct URLs with correct IDs
- Back button works correctly after each navigation
- Deep linking works (direct URL access to any page with auth)
- Breadcrumbs reflect actual navigation path
- 404 page shown for non-existent routes (not crash)
- After login, user redirected to intended destination (or dashboard)
- After logout, user redirected to login page
- Pagination links work and preserve current filters
- Tab navigation within pages works correctly
- Modal close buttons return to previous state
- Cancel buttons on forms return to previous page

### C. Real Data Verification Features

Test that data is real (not mocked) and persists correctly.

**Required features (examples):**

- Create a record via UI with unique content → verify it appears in list
- Create a record → refresh page → record still exists
- Create a record → log out → log in → record still exists
- Edit a record → verify changes persist after refresh
- Delete a record → verify it's gone from list AND database
- Delete a record → verify it's gone from related dropdowns
- Filter/search → results match actual data created in test
- Dashboard statistics reflect real record counts (create 3 items, count shows 3)
- Reports show real aggregated data
- Export functionality exports actual data you created
- Related records update when parent changes
- Timestamps are real and accurate (created_at, updated_at)
- Data created by User A is not visible to User B (unless shared)
- Empty state shows correctly when no data exists

### D. Workflow Completeness Features

Test that every workflow can be completed end-to-end through the UI.

**Required features (examples):**

- Every entity has working Create operation via UI form
- Every entity has working Read/View operation (detail page loads)
- Every entity has working Update operation (edit form saves)
- Every entity has working Delete operation (with confirmation dialog)
- Every status/state has a UI mechanism to transition to next state
- Multi-step processes (wizards) can be completed end-to-end
- Bulk operations (select all, delete selected) work
- Cancel/Undo operations work where applicable
- Required fields prevent submission when empty
- Form validation shows errors before submission
- Successful submission shows success feedback
- Backend workflow (e.g., user→customer conversion) has UI trigger

### E. Error Handling Features

Test graceful handling of errors and edge cases.

**Required features (examples):**

- Network failure shows user-friendly error message, not crash
- Invalid form input shows field-level errors
- API errors display meaningful messages to user
- 404 responses handled gracefully (show not found page)
- 500 responses don't expose stack traces or technical details
- Empty search results show "no results found" message
- Loading states shown during all async operations
- Timeout doesn't hang the UI indefinitely
- Submitting form with server error keeps user data in form
- File upload errors (too large, wrong type) show clear message
- Duplicate entry errors (e.g., email already exists) are clear

### F. UI-Backend Integration Features

Test that frontend and backend communicate correctly.

**Required features (examples):**

- Frontend request format matches what backend expects
- Backend response format matches what frontend parses
- All dropdown options come from real database data (not hardcoded)
- Related entity selectors (e.g., "choose category") populated from DB
- Changes in one area reflect in related areas after refresh
- Deleting parent handles children correctly (cascade or block)
- Filters work with actual data attributes from database
- Sort functionality sorts real data correctly
- Pagination returns correct page of real data
- API error responses are parsed and displayed correctly
- Loading spinners appear during API calls
- Optimistic updates (if used) rollback on failure

### G. State & Persistence Features

Test that state is maintained correctly across sessions and tabs.

**Required features (examples):**

- Refresh page mid-form - appropriate behavior (data kept or cleared)
- Close browser, reopen - session state handled correctly
- Same user in two browser tabs - changes sync or handled gracefully
- Browser back after form submit - no duplicate submission
- Bookmark a page, return later - works (with auth check)
- LocalStorage/cookies cleared - graceful re-authentication
- Unsaved changes warning when navigating away from dirty form

### H. URL & Direct Access Features

Test direct URL access and URL manipulation security.

**Required features (examples):**

- Change entity ID in URL - cannot access others' data
- Access /admin directly as regular user - blocked
- Malformed URL parameters - handled gracefully (no crash)
- Very long URL - handled correctly
- URL with SQL injection attempt - rejected/sanitized
- Deep link to deleted entity - shows "not found", not crash
- Query parameters for filters are reflected in UI
- Sharing a URL with filters preserves those filters

### I. Double-Action & Idempotency Features

Test that rapid or duplicate actions don't cause issues.

**Required features (examples):**

- Double-click submit button - only one record created
- Rapid multiple clicks on delete - only one deletion occurs
- Submit form, hit back, submit again - appropriate behavior
- Multiple simultaneous API calls - server handles correctly
- Refresh during save operation - data not corrupted
- Click same navigation link twice quickly - no issues
- Submit button disabled during processing

### J. Data Cleanup & Cascade Features

Test that deleting data cleans up properly everywhere.

**Required features (examples):**

- Delete parent entity - children removed from all views
- Delete item - removed from search results immediately
- Delete item - statistics/counts updated immediately
- Delete item - related dropdowns updated
- Delete item - cached views refreshed
- Soft delete (if applicable) - item hidden but recoverable
- Hard delete - item completely removed from database

### K. Default & Reset Features

Test that defaults and reset functionality work correctly.

**Required features (examples):**

- New form shows correct default values
- Date pickers default to sensible dates (today, not 1970)
- Dropdowns default to correct option (or placeholder)
- Reset button clears to defaults, not just empty
- Clear filters button resets all filters to default
- Pagination resets to page 1 when filters change
- Sorting resets when changing views

### L. Search & Filter Edge Cases

Test search and filter functionality thoroughly.

**Required features (examples):**

- Empty search shows all results (or appropriate message)
- Search with only spaces - handled correctly
- Search with special characters (!@#$%^&\*) - no errors
- Search with quotes - handled correctly
- Search with very long string - handled correctly
- Filter combinations that return zero results - shows message
- Filter + search + sort together - all work correctly
- Filter persists after viewing detail and returning to list
- Clear individual filter - works correctly
- Search is case-insensitive (or clearly case-sensitive)

### M. Form Validation Features

Test all form validation rules exhaustively.

**Required features (examples):**

- Required field empty - shows error, blocks submit
- Email field with invalid email formats - shows error
- Password field - enforces complexity requirements
- Numeric field with letters - rejected
- Date field with invalid date - rejected
- Min/max length enforced on text fields
- Min/max values enforced on numeric fields
- Duplicate unique values rejected (e.g., duplicate email)
- Error messages are specific (not just "invalid")
- Errors clear when user fixes the issue
- Server-side validation matches client-side
- Whitespace-only input rejected for required fields

### N. Feedback & Notification Features

Test that users get appropriate feedback for all actions.

**Required features (examples):**

- Every successful save/create shows success feedback
- Every failed action shows error feedback
- Loading spinner during every async operation
- Disabled state on buttons during form submission
- Progress indicator for long operations (file upload)
- Toast/notification disappears after appropriate time
- Multiple notifications don't overlap incorrectly
- Success messages are specific (not just "Success")

### O. Responsive & Layout Features

Test that the UI works on different screen sizes.

**Required features (examples):**

- Desktop layout correct at 1920px width
- Tablet layout correct at 768px width
- Mobile layout correct at 375px width
- No horizontal scroll on any standard viewport
- Touch targets large enough on mobile (44px min)
- Modals fit within viewport on mobile
- Long text truncates or wraps correctly (no overflow)
- Tables scroll horizontally if needed on mobile
- Navigation collapses appropriately on mobile

### P. Accessibility Features

Test basic accessibility compliance.

**Required features (examples):**

- Tab navigation works through all interactive elements
- Focus ring visible on all focused elements
- Screen reader can navigate main content areas
- ARIA labels on icon-only buttons
- Color contrast meets WCAG AA (4.5:1 for text)
- No information conveyed by color alone
- Form fields have associated labels
- Error messages announced to screen readers
- Skip link to main content (if applicable)
- Images have alt text

### Q. Temporal & Timezone Features

Test date/time handling.

**Required features (examples):**

- Dates display in user's local timezone
- Created/updated timestamps accurate and formatted correctly
- Date picker allows only valid date ranges
- Overdue items identified correctly (timezone-aware)
- "Today", "This Week" filters work correctly for user's timezone
- Recurring items generate at correct times (if applicable)
- Date sorting works correctly across months/years

### R. Concurrency & Race Condition Features

Test multi-user and race condition scenarios.

**Required features (examples):**

- Two users edit same record - last save wins or conflict shown
- Record deleted while another user viewing - graceful handling
- List updates while user on page 2 - pagination still works
- Rapid navigation between pages - no stale data displayed
- API response arrives after user navigated away - no crash
- Concurrent form submissions from same user handled

### S. Export/Import Features (if applicable)

Test data export and import functionality.

**Required features (examples):**

- Export all data - file contains all records
- Export filtered data - only filtered records included
- Import valid file - all records created correctly
- Import duplicate data - handled correctly (skip/update/error)
- Import malformed file - error message, no partial import
- Export then import - data integrity preserved exactly

### T. Performance Features

Test basic performance requirements.

**Required features (examples):**

- Page loads in <3s with 100 records
- Page loads in <5s with 1000 records
- Search responds in <1s
- Infinite scroll doesn't degrade with many items
- Large file upload shows progress
- Memory doesn't leak on long sessions
- No console errors during normal operation

---

## ABSOLUTE PROHIBITION: NO MOCK DATA

Features must include tests that **actively verify real data** and **detect mock data patterns**.

**Include these specific features:**

1. Create unique test data (e.g., "TEST_12345_VERIFY_ME")
2. Verify that EXACT data appears in UI
3. Refresh page - data persists
4. Delete data - verify it's gone
5. If data appears that wasn't created during test - FLAG AS MOCK DATA

**The agent implementing features MUST NOT use:**

- Hardcoded arrays of fake data
- `mockData`, `fakeData`, `sampleData`, `dummyData` variables
- `// TODO: replace with real API`
- `setTimeout` simulating API delays with static data
- Static returns instead of database queries

---

**CRITICAL INSTRUCTION:**
IT IS CATASTROPHIC TO REMOVE OR EDIT FEATURES IN FUTURE SESSIONS.
Features can ONLY be marked as complete (via `bd close <feature-id>`).
Never remove features, never edit descriptions, never modify testing steps.
This ensures no functionality is missed.

### SECOND TASK: Create init.sh

Create a script called `init.sh` that future agents can use to quickly
set up and run the development environment. The script should:

1. Install any required dependencies
2. Start any necessary servers or services
3. Print helpful information about how to access the running application

Base the script on the technology stack specified in `prompts/app_spec.txt`.

### THIRD TASK: Initialize Git

Create a git repository and make your first commit with:

- init.sh (environment setup script)
- README.md (project overview and setup instructions)
- Any initial project structure files
- .beads/ directory (feature tracking)

Commit message: "Initial setup: init.sh, project structure, and features"

### FOURTH TASK: Create Project Structure

Set up the basic project structure based on what's specified in `prompts/app_spec.txt`.
This typically includes directories for frontend, backend, and any other
components mentioned in the spec.

### OPTIONAL: Start Implementation

If you have time remaining in this session, you may begin implementing
the highest-priority features. Get the next available feature with:

```bash
bd ready
```

Then claim it:

```bash
bd update <feature-id> --status=in_progress
```

Remember:
- Work on ONE feature at a time
- Test thoroughly before marking as complete
- Commit your progress before session ends

### ENDING THIS SESSION

Before your context fills up:

1. Commit all work with descriptive messages
2. Sync beads: `bd sync`
3. Verify features were created: `bd stats`
4. Leave the environment in a clean, working state

The next agent will continue from here with a fresh context window.

---

**Remember:** You have unlimited time across many sessions. Focus on
quality over speed. Production-ready is the goal.
