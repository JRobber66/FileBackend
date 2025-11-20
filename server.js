const express = require('express');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const jwt = require('jsonwebtoken');

const app = express();
const upload = multer({ dest: 'temp_chunks/' });
app.use(express.json());

// Config
const PORT = 3000;  // Railway will override this automatically if you bind to process.env.PORT
const JWT_SECRET = "supersecret"; // Replace with your own secret

// Load or create users file
const USERS_FILE = 'users.json';
if (!fs.existsSync(USERS_FILE)) fs.writeFileSync(USERS_FILE, JSON.stringify({}));
let users = JSON.parse(fs.readFileSync(USERS_FILE));

// Utility: save users.json
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

// Upload endpoint
app.post('/upload', upload.single('chunk'), (req, res) => {
  const { fileName, chunkIndex, totalChunks } = req.body;
  const chunkPath = req.file.path;
  const fileDir = path.join('uploads', fileName);

  if (!fs.existsSync(fileDir)) fs.mkdirSync(fileDir, { recursive: true });
  fs.renameSync(chunkPath, path.join(fileDir, `chunk_${chunkIndex}`));

  const uploadedChunks = fs.readdirSync(fileDir);
  if (uploadedChunks.length == totalChunks) {
    const finalPath = path.join('uploads', fileName);
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
  const filePath = path.join('uploads', req.params.fileName);
  if (!fs.existsSync(filePath)) return res.status(404).send({ error: 'File not found' });
  res.download(filePath);
});

// Start server
const port = process.env.PORT || PORT;
app.listen(port, () => console.log(`Backend running on port ${port}`));
