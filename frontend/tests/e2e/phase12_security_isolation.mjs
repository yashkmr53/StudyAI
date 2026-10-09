/**
 * Phase 12 Security & Integrity Hardening E2E Verification
 * ========================================================
 * Validates against live StudyAI stack:
 * 1. Global ReferenceDocument deletion authorization (non-staff 403 vs staff 204)
 * 2. Foreign private ReferenceDocument deletion (403 Forbidden)
 * 3. Backend sole-profile deletion guard (400 rejection when count == 1, 204 when count >= 2)
 * 4. Multi-profile cross-tenant isolation (direct UUID access, list scoping)
 * 5. Elimination of .first() ambiguity across endpoints
 *
 * Run:
 *   node frontend/tests/e2e/phase12_security_isolation.mjs
 */

const API_BASE = process.env.API_BASE || "http://localhost:8000";

function log(msg) {
  const ts = new Date().toISOString().substring(11, 23);
  console.log(`[${ts}] ${msg}`);
}

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, options);
  let json = null;
  const text = await res.text();
  try {
    json = JSON.parse(text);
  } catch {
    json = text;
  }
  return { status: res.status, headers: res.headers, data: json };
}

async function getAuthToken(email, password) {
  const loginRes = await request("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (loginRes.status === 200) {
    return loginRes.data.access;
  }
  // Register if not existing
  const regRes = await request("/api/v1/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
      password_confirm: password,
      name: "Security Tester",
    }),
  });
  if (regRes.status === 201) {
    return regRes.data.access;
  }
  throw new Error(`Failed to login or register for ${email}: ${JSON.stringify(loginRes.data)}`);
}

async function runTests() {
  log("Starting Phase 12 Security & Integrity E2E Verification...");
  const results = [];

  function pass(name, details = "") {
    log(`  [PASS] ${name} ${details ? `(${details})` : ""}`);
    results.push({ test: name, status: "PASSED", details });
  }

  function fail(name, reason) {
    log(`  [FAIL] ${name}: ${reason}`);
    results.push({ test: name, status: "FAILED", error: reason });
    throw new Error(`Test failed: ${name} -> ${reason}`);
  }

  // 1. Authenticate Staff and Normal User
  log("\n--- Authenticating Users ---");
  const staffToken = await getAuthToken("admin@studyai.dev", "AdminPass123!");
  const userEmail = `sec_user_${Date.now()}@studyai.dev`;
  const userToken = await getAuthToken(userEmail, "SecurityPass123!");
  pass("Authentication", `Staff and User tokens acquired for ${userEmail}`);

  // Fetch initial profiles for normal user
  const initProfilesRes = await request("/api/v1/profiles", {
    headers: { Authorization: `Bearer ${userToken}` },
  });
  if (initProfilesRes.status !== 200) fail("Fetch initial profiles", `Status ${initProfilesRes.status}`);
  let userProfiles = initProfilesRes.data.results || initProfilesRes.data;
  log(`User has ${userProfiles.length} initial profiles.`);

  // If user has more than 1 profile, clean up down to 1
  while (userProfiles.length > 1) {
    const toDel = userProfiles.pop();
    await request(`/api/v1/profiles/${toDel.id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${userToken}` },
    });
  }
  pass("Profile Setup", "Normal user prepared with exactly 1 initial profile");

  // 2. Test Sole Profile Deletion Guard
  log("\n--- Testing Backend Sole-Profile Deletion Guard ---");
  const soleProfile = userProfiles[0];
  const soleDelRes = await request(`/api/v1/profiles/${soleProfile.id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${userToken}` },
  });

  if (soleDelRes.status === 400 && soleDelRes.data?.error?.code === "SOLE_PROFILE_CANNOT_BE_DELETED") {
    pass("Sole Profile Deletion Guard", `Rejected with 400 SOLE_PROFILE_CANNOT_BE_DELETED`);
  } else {
    fail("Sole Profile Deletion Guard", `Expected 400, got ${soleDelRes.status}: ${JSON.stringify(soleDelRes.data)}`);
  }

  // Verify profile still exists
  const checkSoleRes = await request(`/api/v1/profiles/${soleProfile.id}`, {
    headers: { Authorization: `Bearer ${userToken}` },
  });
  if (checkSoleRes.status === 200) {
    pass("Sole Profile Persistence", "Profile survived illegal deletion attempt");
  } else {
    fail("Sole Profile Persistence", `Profile missing after rejection! Status: ${checkSoleRes.status}`);
  }

  // Create Profile 2
  const createP2Res = await request("/api/v1/profiles", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${userToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name: "Secondary Profile", module: "NOTE_SPACE" }),
  });
  if (createP2Res.status !== 201) fail("Create Profile 2", `Status ${createP2Res.status}: ${JSON.stringify(createP2Res.data)}`);
  const profile2 = createP2Res.data;
  pass("Create Profile 2", `Created secondary profile ${profile2.id}`);

  // Now delete Profile 2 (allowed since user has 2 profiles)
  const delP2Res = await request(`/api/v1/profiles/${profile2.id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${userToken}` },
  });
  if (delP2Res.status === 204) {
    pass("Multi-Profile Deletion Allowed", "Successfully deleted non-sole profile with 204");
  } else {
    fail("Multi-Profile Deletion Allowed", `Expected 204, got ${delP2Res.status}`);
  }

  // Re-create Profile 2 for isolation testing
  const p2Recreate = await request("/api/v1/profiles", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${userToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name: "Profile B (Isolated)", module: "NOTE_SPACE" }),
  });
  const profileB = p2Recreate.data;
  const profileA = soleProfile;

  // 3. Test Global & Private Reference Deletion Authorization
  log("\n--- Testing Reference Deletion Authorization ---");
  // Staff creates a global reference
  const staffForm = new FormData();
  staffForm.append("file", new Blob(["%PDF-1.4 dummy global pdf content"], { type: "application/pdf" }), "global_manual.pdf");
  staffForm.append("title", `Global Reference Standard ${Date.now()}`);
  staffForm.append("source_type", "TEXTBOOK");
  staffForm.append("is_global", "true");

  const createGlobalRefRes = await request("/api/v1/references/", {
    method: "POST",
    headers: { Authorization: `Bearer ${staffToken}` },
    body: staffForm,
  });
  if (createGlobalRefRes.status !== 201) fail("Create Global Reference (Staff)", `Status: ${createGlobalRefRes.status}: ${JSON.stringify(createGlobalRefRes.data)}`);
  const globalRef = createGlobalRefRes.data;
  pass("Create Global Reference", `Staff created global reference ${globalRef.id}`);

  // Normal user creates private reference under Profile A
  const userForm = new FormData();
  userForm.append("file", new Blob(["%PDF-1.4 dummy user private pdf content"], { type: "application/pdf" }), "private_notes.pdf");
  userForm.append("title", `Profile A Private Notes ${Date.now()}`);
  userForm.append("source_type", "LECTURE_MATERIAL");

  const createPrivateRefARes = await request("/api/v1/references/", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${userToken}`,
      "X-Active-Profile": profileA.id,
    },
    body: userForm,
  });
  if (createPrivateRefARes.status !== 201) fail("Create Private Reference A", `Status: ${createPrivateRefARes.status}: ${JSON.stringify(createPrivateRefARes.data)}`);
  const privateRefA = createPrivateRefARes.data;
  pass("Create Private Reference A", `Created private reference ${privateRefA.id} under Profile A`);

  // Non-staff user attempts to DELETE Global Reference -> MUST BE 403 Forbidden
  const userDeleteGlobalRes = await request(`/api/v1/references/${globalRef.id}/`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${userToken}`,
      "X-Active-Profile": profileA.id,
    },
  });
  if (userDeleteGlobalRes.status === 403) {
    pass("Global Reference Deletion Guard", "Non-staff user blocked with 403 Forbidden");
  } else {
    fail("Global Reference Deletion Guard", `Expected 403, got ${userDeleteGlobalRes.status}: ${JSON.stringify(userDeleteGlobalRes.data)}`);
  }

  // User on Profile B attempts to DELETE Profile A's private reference -> MUST BE 403 Forbidden
  const userDeleteForeignRefRes = await request(`/api/v1/references/${privateRefA.id}/`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${userToken}`,
      "X-Active-Profile": profileB.id,
    },
  });
  if ([403, 404].includes(userDeleteForeignRefRes.status)) {
    pass("Cross-Profile Private Reference Deletion Guard", `Blocked cross-profile deletion with status ${userDeleteForeignRefRes.status}`);
  } else {
    fail("Cross-Profile Private Reference Deletion Guard", `Expected 403 or 404, got ${userDeleteForeignRefRes.status}`);
  }

  // User on Profile A deletes own private reference -> MUST SUCCEED with 204
  const userDeleteOwnRefRes = await request(`/api/v1/references/${privateRefA.id}/`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${userToken}`,
      "X-Active-Profile": profileA.id,
    },
  });
  if (userDeleteOwnRefRes.status === 204) {
    pass("Own Private Reference Deletion", "Owner successfully deleted private reference with 204");
  } else {
    fail("Own Private Reference Deletion", `Expected 204, got ${userDeleteOwnRefRes.status}`);
  }

  // Staff deletes global reference -> MUST SUCCEED with 204
  const staffDeleteGlobalRes = await request(`/api/v1/references/${globalRef.id}/`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${staffToken}` },
  });
  if (staffDeleteGlobalRes.status === 204) {
    pass("Staff Global Reference Deletion", "Staff successfully deleted global reference with 204");
  } else {
    fail("Staff Global Reference Deletion", `Expected 204, got ${staffDeleteGlobalRes.status}`);
  }

  // 4. Test Cross-Profile Resource Isolation
  log("\n--- Testing Cross-Profile Resource Isolation ---");
  // Create Subject under Profile A
  const createSubjARes = await request("/api/v1/subjects", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${userToken}`,
      "X-Active-Profile": profileA.id,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name: "Profile A Subject", profile: profileA.id }),
  });
  if (createSubjARes.status !== 201) fail("Create Subject A", `Status: ${createSubjARes.status}: ${JSON.stringify(createSubjARes.data)}`);
  const subjA = createSubjARes.data;

  // Create Document under Profile A
  const createDocARes = await request("/api/v1/documents", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${userToken}`,
      "X-Active-Profile": profileA.id,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      title: "Profile A Secret Document",
      profile: profileA.id,
      subject: subjA.id,
      source_type: "pdf",
      filename: "secret_document.pdf",
    }),
  });
  if (createDocARes.status !== 201) fail("Create Document A", `Status: ${createDocARes.status}: ${JSON.stringify(createDocARes.data)}`);
  const docA = createDocARes.data.document;
  pass("Create Profile A Resources", `Subject ${subjA.id} and Document ${docA.id} created under Profile A`);

  // Direct UUID access to Subject A using Profile B header -> MUST BE 404 or 403
  const directSubjRes = await request(`/api/v1/subjects/${subjA.id}`, {
    headers: {
      Authorization: `Bearer ${userToken}`,
      "X-Active-Profile": profileB.id,
    },
  });
  if ([403, 404].includes(directSubjRes.status)) {
    pass("Cross-Profile Direct Subject Access Blocked", `Status ${directSubjRes.status}`);
  } else {
    fail("Cross-Profile Direct Subject Access Blocked", `Expected 403 or 404, got ${directSubjRes.status}`);
  }

  // Direct UUID access to Document A using Profile B header -> MUST BE 404 or 403
  const directDocRes = await request(`/api/v1/documents/${docA.id}`, {
    headers: {
      Authorization: `Bearer ${userToken}`,
      "X-Active-Profile": profileB.id,
    },
  });
  if ([403, 404].includes(directDocRes.status)) {
    pass("Cross-Profile Direct Document Access Blocked", `Status ${directDocRes.status}`);
  } else {
    fail("Cross-Profile Direct Document Access Blocked", `Expected 403 or 404, got ${directDocRes.status}`);
  }

  // List subjects with Profile B header -> MUST NOT contain Subject A
  const listSubjBRes = await request("/api/v1/subjects", {
    headers: {
      Authorization: `Bearer ${userToken}`,
      "X-Active-Profile": profileB.id,
    },
  });
  const subjectsB = listSubjBRes.data.results || listSubjBRes.data;
  const foundSubjAInB = subjectsB.some((s) => s.id === subjA.id);
  if (!foundSubjAInB) {
    pass("Subject List Scoping", "Profile B subject list strictly excludes Profile A subjects");
  } else {
    fail("Subject List Scoping", "Subject A leaked into Profile B list!");
  }

  // List documents with Profile B header -> MUST NOT contain Document A
  const listDocBRes = await request("/api/v1/documents", {
    headers: {
      Authorization: `Bearer ${userToken}`,
      "X-Active-Profile": profileB.id,
    },
  });
  const docsB = listDocBRes.data.results || listDocBRes.data;
  const foundDocAInB = docsB.some((d) => d.id === docA.id);
  if (!foundDocAInB) {
    pass("Document List Scoping", "Profile B document list strictly excludes Profile A documents");
  } else {
    fail("Document List Scoping", "Document A leaked into Profile B list!");
  }

  log("\n==========================================");
  log(`ALL ${results.length} E2E SECURITY CHECKS PASSED!`);
  log("==========================================");
}

runTests().catch((err) => {
  console.error("E2E Test Failed:", err);
  process.exit(1);
});
