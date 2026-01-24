# Feature Examples Reference

This document provides detailed examples for each feature category. Use these as inspiration when creating features - adapt them to your specific project.

---

## Security & Access Control

Test unauthorized access blocking and permission enforcement.

**Web App / API Examples:**
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
- Failed login attempts handled (no information leakage)

**Backend Examples:**
- API keys validated before processing requests
- Rate limiting prevents abuse
- Input sanitization prevents injection attacks
- Secrets not logged or exposed in error messages

---

## Navigation Integrity (Web App)

Test every button, link, and menu item goes to the correct place.

- Every sidebar button navigates to correct page
- Every menu item links to existing route
- All CRUD action buttons (Edit, Delete, View) go to correct URLs with correct IDs
- Back button works correctly after each navigation
- Deep linking works (direct URL access with auth)
- Breadcrumbs reflect actual navigation path
- 404 page shown for non-existent routes (not crash)
- After login, user redirected to intended destination (or dashboard)
- After logout, user redirected to login page
- Pagination links work and preserve current filters
- Tab navigation within pages works correctly
- Modal close buttons return to previous state
- Cancel buttons on forms return to previous page

---

## Real Data Verification

Test data is real (not mocked) and persists correctly.

- Create record via UI with unique content → verify it appears in list
- Create record → refresh page → record still exists
- Create record → log out → log in → record still exists
- Edit record → verify changes persist after refresh
- Delete record → verify gone from list AND database
- Delete record → verify gone from related dropdowns
- Filter/search → results match actual data created in test
- Dashboard statistics reflect real record counts
- Reports show real aggregated data
- Export functionality exports actual data you created
- Related records update when parent changes
- Timestamps are real and accurate (created_at, updated_at)
- Data created by User A not visible to User B (unless shared)
- Empty state shows correctly when no data exists

---

## Workflow Completeness

Test every workflow can be completed end-to-end.

**CRUD Operations:**
- Every entity has working Create operation via UI form
- Every entity has working Read/View operation (detail page loads)
- Every entity has working Update operation (edit form saves)
- Every entity has working Delete operation (with confirmation)

**State Transitions:**
- Every status/state has UI mechanism to transition to next state
- Multi-step processes (wizards) complete end-to-end
- Bulk operations (select all, delete selected) work
- Cancel/Undo operations work where applicable
- Required fields prevent submission when empty
- Form validation shows errors before submission
- Successful submission shows success feedback
- Backend workflows (e.g., user→customer conversion) have UI trigger

---

## Error Handling

Test graceful handling of errors and edge cases.

**UI/API Examples:**
- Network failure shows user-friendly error message, not crash
- Invalid form input shows field-level errors
- API errors display meaningful messages to user
- 404 responses handled gracefully (show not found page)
- 500 responses don't expose stack traces
- Empty search results show "no results found" message
- Loading states shown during all async operations
- Timeout doesn't hang UI indefinitely
- Submitting form with server error keeps user data in form
- File upload errors (too large, wrong type) show clear message
- Duplicate entry errors (email exists) are clear

**Backend/CLI Examples:**
- Invalid input file format shows descriptive error
- Missing required configuration fails fast with clear message
- Network errors during external API calls are retried or reported
- Out of memory handled gracefully (not silent crash)
- Partial failure reports which items succeeded/failed

---

## UI-Backend Integration

Test frontend and backend communicate correctly.

- Frontend request format matches backend expectation
- Backend response format matches frontend parsing
- All dropdown options come from real database data
- Related entity selectors populated from DB
- Changes in one area reflect in related areas after refresh
- Deleting parent handles children correctly (cascade or block)
- Filters work with actual data attributes from database
- Sort functionality sorts real data correctly
- Pagination returns correct page of real data
- API error responses parsed and displayed correctly
- Loading spinners appear during API calls
- Optimistic updates rollback on failure

---

## State & Persistence

Test state maintained correctly across sessions and tabs.

- Refresh page mid-form - appropriate behavior
- Close browser, reopen - session state handled correctly
- Same user in two browser tabs - changes sync or handled gracefully
- Browser back after form submit - no duplicate submission
- Bookmark a page, return later - works (with auth check)
- LocalStorage/cookies cleared - graceful re-authentication
- Unsaved changes warning when navigating away from dirty form

---

## URL & Direct Access

Test direct URL access and URL manipulation security.

- Change entity ID in URL - cannot access others' data
- Access /admin directly as regular user - blocked
- Malformed URL parameters - handled gracefully (no crash)
- Very long URL - handled correctly
- URL with SQL injection attempt - rejected/sanitized
- Deep link to deleted entity - shows "not found", not crash
- Query parameters for filters reflected in UI
- Sharing URL with filters preserves those filters

---

## Double-Action & Idempotency

Test rapid or duplicate actions don't cause issues.

- Double-click submit button - only one record created
- Rapid multiple clicks on delete - only one deletion occurs
- Submit form, hit back, submit again - appropriate behavior
- Multiple simultaneous API calls - server handles correctly
- Refresh during save operation - data not corrupted
- Click same navigation link twice quickly - no issues
- Submit button disabled during processing

---

## Data Cleanup & Cascade

Test deleting data cleans up properly everywhere.

- Delete parent entity - children removed from all views
- Delete item - removed from search results immediately
- Delete item - statistics/counts updated immediately
- Delete item - related dropdowns updated
- Delete item - cached views refreshed
- Soft delete (if applicable) - item hidden but recoverable
- Hard delete - item completely removed from database

---

## Default & Reset

Test defaults and reset functionality work correctly.

- New form shows correct default values
- Date pickers default to sensible dates (today, not 1970)
- Dropdowns default to correct option (or placeholder)
- Reset button clears to defaults, not just empty
- Clear filters button resets all filters to default
- Pagination resets to page 1 when filters change
- Sorting resets when changing views

---

## Search & Filter Edge Cases

Test search and filter functionality thoroughly.

- Empty search shows all results (or appropriate message)
- Search with only spaces - handled correctly
- Search with special characters (!@#$%^&*) - no errors
- Search with quotes - handled correctly
- Search with very long string - handled correctly
- Filter combinations returning zero results - shows message
- Filter + search + sort together - all work correctly
- Filter persists after viewing detail and returning to list
- Clear individual filter - works correctly
- Search is case-insensitive (or clearly case-sensitive)

---

## Form Validation

Test all form validation rules exhaustively.

- Required field empty - shows error, blocks submit
- Email field with invalid formats - shows error
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

---

## Feedback & Notification

Test users get appropriate feedback for all actions.

- Every successful save/create shows success feedback
- Every failed action shows error feedback
- Loading spinner during every async operation
- Disabled state on buttons during form submission
- Progress indicator for long operations (file upload)
- Toast/notification disappears after appropriate time
- Multiple notifications don't overlap incorrectly
- Success messages are specific (not just "Success")

---

## Responsive & Layout

Test UI works on different screen sizes.

- Desktop layout correct at 1920px width
- Tablet layout correct at 768px width
- Mobile layout correct at 375px width
- No horizontal scroll on any standard viewport
- Touch targets large enough on mobile (44px min)
- Modals fit within viewport on mobile
- Long text truncates or wraps correctly (no overflow)
- Tables scroll horizontally if needed on mobile
- Navigation collapses appropriately on mobile

---

## Accessibility

Test basic accessibility compliance.

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

---

## Temporal & Timezone

Test date/time handling.

- Dates display in user's local timezone
- Created/updated timestamps accurate and formatted correctly
- Date picker allows only valid date ranges
- Overdue items identified correctly (timezone-aware)
- "Today", "This Week" filters work correctly for user's timezone
- Recurring items generate at correct times (if applicable)
- Date sorting works correctly across months/years

---

## Concurrency & Race Conditions

Test multi-user and race condition scenarios.

- Two users edit same record - last save wins or conflict shown
- Record deleted while another user viewing - graceful handling
- List updates while user on page 2 - pagination still works
- Rapid navigation between pages - no stale data displayed
- API response arrives after user navigated away - no crash
- Concurrent form submissions from same user handled

---

## Export/Import

Test data export and import functionality.

- Export all data - file contains all records
- Export filtered data - only filtered records included
- Import valid file - all records created correctly
- Import duplicate data - handled correctly (skip/update/error)
- Import malformed file - error message, no partial import
- Export then import - data integrity preserved exactly

---

## Performance

Test basic performance requirements.

- Page loads in <3s with 100 records
- Page loads in <5s with 1000 records
- Search responds in <1s
- Infinite scroll doesn't degrade with many items
- Large file upload shows progress
- Memory doesn't leak on long sessions
- No console errors during normal operation

---

## Backend/Processing-Specific Features

### Input/Output Handling
- Accepts all documented input formats
- Rejects undocumented formats with clear error
- Handles empty input gracefully
- Handles maximum size input without crash
- Output format matches specification exactly
- Streaming input/output works for large data

### Processing Correctness
- Edge case: minimum valid input
- Edge case: maximum valid input
- Edge case: boundary conditions (off-by-one)
- Handles unicode/special characters correctly
- Maintains data integrity through transformations
- Deterministic output for same input

### Resource Limits
- Memory usage stays within bounds under load
- CPU usage doesn't spike indefinitely
- Timeout handling for long operations
- Backpressure handling when overwhelmed
- Graceful degradation under resource pressure

### Graceful Shutdown
- SIGTERM triggers clean shutdown
- SIGINT triggers clean shutdown
- In-progress work is completed or safely abandoned
- Resources (files, connections) properly closed
- Shutdown completes within timeout

### Monitoring & Health
- Health check endpoint returns accurate status
- Metrics exported in expected format
- Logs include correlation IDs for tracing
- Error counts increment on failures
- Status reflects actual processing state

### CLI-Specific Features
- --help shows usage information
- --version shows version number
- Invalid arguments show helpful error
- Required arguments validated upfront
- Exit codes follow conventions (0=success, 1=error)
- Stdin/stdout piping works correctly
- Long-running operations show progress

### Library-Specific Features
- Public API matches documentation
- Types are correctly exported
- Dependencies are minimal and documented
- Errors are properly typed/documented
- Thread safety documented and enforced
- Memory management follows conventions
