const SHEET_ID = '1Mj8AQqTAcwOERolWsoq0nT2usSfZ8AEOBGAiUKkmQkA';

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    const route = body.route;

    if (route === 'auth') return json(doAuth(body));
    if (route === 'progress_get') return json(doProgressGet(body));
    if (route === 'progress') return json(doProgress(body));
    if (route === 'test') return json(doTest(body));
    if (route === 'admin_data') return json(doAdminData());

    return json({ ok: false, error: 'Unknown route' });
  } catch (err) {
    return json({ ok: false, error: err.message });
  }
}

function doGet(e) {
  return json({ ok: true, service: 'mamasloft-training' });
}

function doAuth(body) {
  const pin = String(body.pin).trim();
  const ss = SpreadsheetApp.openById(SHEET_ID);
  const svod = ss.getSheetByName('Свод ');
  const data = svod.getDataRange().getValues();

  for (var i = 0; i < data.length; i++) {
    var rowPin = String(data[i][2]).trim();
    if (rowPin === pin) {
      var status = String(data[i][5] || '').trim();
      var role = (status === 'Админ') ? 'admin' : 'consultant';
      return { ok: true, name: String(data[i][1]).trim(), role: role };
    }
  }
  return { ok: false, error: 'Invalid PIN' };
}

function doProgressGet(body) {
  const pin = String(body.pin).trim();
  const ss = SpreadsheetApp.openById(SHEET_ID);

  var userName = findUserName(ss, pin);
  if (!userName) return { ok: false, error: 'User not found' };

  var status = ss.getSheetByName('Статус обучения');
  var data = status.getDataRange().getValues();
  var header = data[0];

  var colIdx = -1;
  for (var c = 2; c < header.length; c++) {
    if (String(header[c]).trim() === userName) { colIdx = c; break; }
  }
  if (colIdx === -1) return { ok: true, progress: {} };

  var progress = {};
  for (var r = 1; r < data.length; r++) {
    var topic = String(data[r][0]).trim();
    var stage = String(data[r][1]).trim();
    var val = data[r][colIdx];

    if (val === '' || val === null || val === undefined) continue;

    if (!progress[topic]) progress[topic] = {};

    var stageKey = stageNameToKey(stage);
    if (stageKey === 'quiz') {
      progress[topic][stageKey] = Number(val);
    } else {
      progress[topic][stageKey] = true;
    }
  }

  return { ok: true, progress: progress };
}

function doProgress(body) {
  var pin = String(body.pin).trim();
  var topic = String(body.topic).trim();
  var stage = String(body.stage).trim();

  var ss = SpreadsheetApp.openById(SHEET_ID);
  var userName = findUserName(ss, pin);
  if (!userName) return { ok: false, error: 'User not found' };

  var status = ss.getSheetByName('Статус обучения');
  var data = status.getDataRange().getValues();
  var header = data[0];

  var colIdx = findUserCol(header, userName);
  if (colIdx === -1) return { ok: false, error: 'User column not found' };

  var stageName = stageKeyToName(stage);
  var rowIdx = findRow(data, topic, stageName);
  if (rowIdx === -1) return { ok: false, error: 'Topic/stage not found' };

  status.getRange(rowIdx + 1, colIdx + 1).setValue('✓');
  updateSvod(ss, pin);

  return { ok: true };
}

function doTest(body) {
  var pin = String(body.pin).trim();
  var topic = String(body.topic).trim();
  var score = Number(body.score);

  var ss = SpreadsheetApp.openById(SHEET_ID);
  var userName = findUserName(ss, pin);
  if (!userName) return { ok: false, error: 'User not found' };

  var status = ss.getSheetByName('Статус обучения');
  var data = status.getDataRange().getValues();
  var header = data[0];

  var colIdx = findUserCol(header, userName);
  if (colIdx === -1) return { ok: false, error: 'User column not found' };

  var rowIdx = findRow(data, topic, 'Тест');
  if (rowIdx === -1) return { ok: false, error: 'Topic/stage not found' };

  status.getRange(rowIdx + 1, colIdx + 1).setValue(score);
  updateSvod(ss, pin);

  return { ok: true };
}

function updateSvod(ss, pin) {
  var userName = findUserName(ss, pin);
  var status = ss.getSheetByName('Статус обучения');
  var data = status.getDataRange().getValues();
  var header = data[0];

  var colIdx = findUserCol(header, userName);
  if (colIdx === -1) return;

  var totalStages = 0;
  var doneStages = 0;
  var quizScores = [];

  for (var r = 1; r < data.length; r++) {
    totalStages++;
    var val = data[r][colIdx];
    if (val !== '' && val !== null && val !== undefined) {
      doneStages++;
      var stage = String(data[r][1]).trim();
      if (stage === 'Тест' && typeof val === 'number') {
        quizScores.push(val);
      }
    }
  }

  var pct = totalStages > 0 ? Math.round(doneStages / totalStages * 100) : 0;
  var avgScore = quizScores.length > 0
    ? Math.round(quizScores.reduce(function(a, b) { return a + b; }, 0) / quizScores.length)
    : 0;

  var svod = ss.getSheetByName('Свод ');
  var svodData = svod.getDataRange().getValues();
  for (var i = 0; i < svodData.length; i++) {
    if (String(svodData[i][2]).trim() === pin) {
      svod.getRange(i + 1, 4).setValue(pct + '%');
      svod.getRange(i + 1, 5).setValue(avgScore + '%');
      break;
    }
  }
}

function findUserName(ss, pin) {
  var svod = ss.getSheetByName('Свод ');
  var data = svod.getDataRange().getValues();
  for (var i = 0; i < data.length; i++) {
    if (String(data[i][2]).trim() === pin) {
      return String(data[i][1]).trim();
    }
  }
  return null;
}

function findUserCol(header, userName) {
  for (var c = 2; c < header.length; c++) {
    if (String(header[c]).trim() === userName) return c;
  }
  return -1;
}

function findRow(data, topic, stageName) {
  for (var r = 1; r < data.length; r++) {
    if (String(data[r][0]).trim() === topic && String(data[r][1]).trim() === stageName) {
      return r;
    }
  }
  return -1;
}

function stageKeyToName(key) {
  if (key === 'lecture') return 'Лекция';
  if (key === 'mindmap') return 'Карта знаний';
  if (key === 'quiz') return 'Тест';
  return key;
}

function stageNameToKey(name) {
  if (name === 'Лекция') return 'lecture';
  if (name === 'Карта знаний') return 'mindmap';
  if (name === 'Тест') return 'quiz';
  return name;
}

function doAdminData() {
  var ss = SpreadsheetApp.openById(SHEET_ID);

  var svod = ss.getSheetByName('Свод ');
  var svodData = svod.getDataRange().getValues();
  var users = [];
  for (var i = 0; i < svodData.length; i++) {
    var name = String(svodData[i][1]).trim();
    var pin = String(svodData[i][2]).trim();
    if (name && pin && /^\d+$/.test(pin)) {
      users.push({ name: name });
    }
  }

  var status = ss.getSheetByName('Статус обучения');
  var statusData = status.getDataRange().getValues();
  var header = statusData[0];

  var modules = [];
  var seen = {};
  for (var r = 1; r < statusData.length; r++) {
    var topic = String(statusData[r][0]).trim();
    if (topic && !seen[topic]) { modules.push(topic); seen[topic] = true; }
  }

  var progress = {};
  for (var c = 2; c < header.length; c++) {
    var userName = String(header[c]).trim();
    if (!userName) continue;
    progress[userName] = {};

    for (var r = 1; r < statusData.length; r++) {
      var topic = String(statusData[r][0]).trim();
      var stage = String(statusData[r][1]).trim();
      var val = statusData[r][c];

      if (!progress[userName][topic]) progress[userName][topic] = {};

      if (val !== '' && val !== null && val !== undefined) {
        var stageKey = stageNameToKey(stage);
        if (stageKey === 'quiz') {
          progress[userName][topic][stageKey] = Number(val);
        } else {
          progress[userName][topic][stageKey] = true;
        }
      }
    }
  }

  return { ok: true, users: users, modules: modules, progress: progress };
}

function json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
