const express = require('express');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const jwt = require('jsonwebtoken');

const app = express();
app.use(express.json());

// Config
const PORT = 3000;
const JWT_SECRET = "supersecret";

// Directories
const TEMP_DIR = 'temp_chunks';
const UPLOADS_DIR = '/app/uploads';

// Ensure folders exist safely
if (!fs.existsSync(TEMP_DIR)) fs.mkdirSync(TEMP_DIR, { recursive: true });
if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR, { recursive: true });

// Multer safe DiskStorage
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, TEMP_DIR); // don't try to create, just use
  },
  filename: (req, file, cb) => {
    cb(null, file.originalname + '-' + Date.now());
  }
});
const upload = multer({ storage });

// Users file
const USERS_FILE = 'users.json';
if (!fs.existsSync(USERS_FILE)) fs.writeFileSync(USERS_FILE, JSON.stringify({}));
let users = JSON.parse(fs.readFileSync(USERS_FILE));

// Save users utility
function saveUsers() {
  fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2));
}

// Signup
app.post('/signup', (req, res) => {
  const { username, password } = req.body;
  if (users[username]) return res.status(400).send({ error: 'User exists' });

  users[username] = password;
  saveUsers();
  res.send({ success: true });
});

// Login
app.post('/login', (req, res) => {
  const { username, password } = req.body;
  if (!users[username] || users[username] !== password)
    return res.status(401).send({ error: 'Invalid credentials' });

  const token = jwt.sign({ username }, JWT_SECRET, { expiresIn: '1h' });
  res.send({ token });
});

// Upload endpoint (chunked)
app.post('/upload', upload.single('chunk'), (req, res) => {
  const { fileName, chunkIndex, totalChunks } = req.body;
  const chunkPath = req.file.path;
  const fileDir = path.join(UPLOADS_DIR, fileName);

  if (!fs.existsSync(fileDir)) fs.mkdirSync(fileDir, { recursive: true });
  fs.renameSync(chunkPath, path.join(fileDir, `chunk_${chunkIndex}`));

  const uploadedChunks = fs.readdirSync(fileDir);
  if (uploadedChunks.length == totalChunks) {
    const finalPath = path.join(UPLOADS_DIR, fileName);
    const writeStream = fs.createWriteStream(finalPath);

    for (let i = 0; i < totalChunks; i++) {
      const data = fs.readFileSync(path.join(fileDir, `chunk_${i}`));
      writeStream.write(data);
      fs.unlinkSync(path.join(fileDir, `chunk_${i}`));
    }
    writeStream.close();
    fs.rmdirSync(fileDir);
    res.send({ message: 'File uploaded', url: `/download/${fileName}` });
  } else {
    res.send({ message: `Chunk ${chunkIndex} uploaded` });
  }
});

// Download endpoint
app.get('/download/:fileName', (req, res) => {
  const filePath = path.join(UPLOADS_DIR, req.params.fileName);
  if (!fs.existsSync(filePath)) return res.status(404).send({ error: 'File not found' });
  res.download(filePath);
});

// Start server
const port = process.env.PORT || PORT;
app.listen(port, () => console.log(`Backend running on port ${port}`));

