import { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';

// 后端 WebSocket 和 API 地址 (根据实际部署情况修改)
// 本地开发时，通常是 ws://localhost:8000 和 http://localhost:8000
const BACKEND_WS_URL = `ws://${window.location.hostname}:8000`;
const BACKEND_API_URL = `http://${window.location.hostname}:8000`;

// 生成随机字符串的辅助函数
const generateRandomId = (length = 8) => {
  return Math.random().toString(36).substring(2, 2 + length);
};

// 生成随机昵称的辅助函数 (简单示例)
const generateRandomName = () => {
  const adjectives = ["快乐的", "勇敢的", "聪明的", "神秘的", "活泼的"];
  const nouns = ["猫咪", "狐狸", "老虎", "小鸟", "开发者"];
  return `${adjectives[Math.floor(Math.random() * adjectives.length)]}${nouns[Math.floor(Math.random() * nouns.length)]}`;
};


function App() {
  const [userId, setUserId] = useState(null);
  const [userName, setUserName] = useState(null);
  const [messages, setMessages] = useState([]); // { id, sender: {id, name}, content, messageType }
  const [users, setUsers] = useState([]); // { id, name }
  const [inputValue, setInputValue] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(true); // 新增状态，用于显示连接中
  const [error, setError] = useState(null); // 用于显示错误信息
  // --- 新增状态用于历史消息加载 ---
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [hasMoreHistory, setHasMoreHistory] = useState(true); // 初始假设有更多历史

  const ws = useRef(null);
  const messagesEndRef = useRef(null); // 用于自动滚动到底部
  const fileInputRef = useRef(null); // 用于触发文件选择
  const messagesAreaRef = useRef(null); // 新增：引用消息显示区域
  const oldestMessageTimestamp = useRef(null); // 新增：记录当前最老消息的时间戳
  const initialLoadComplete = useRef(false); // 新增：标记首次历史加载是否完成

  // --- 用户身份初始化 ---
  useEffect(() => {
    let storedUserId = localStorage.getItem('userId');
    let storedUserName = localStorage.getItem('userName');

    if (!storedUserId || !storedUserName) {
      storedUserId = generateRandomId();
      storedUserName = generateRandomName();
      localStorage.setItem('userId', storedUserId);
      localStorage.setItem('userName', storedUserName);
    }
    setUserId(storedUserId);
    setUserName(storedUserName);
    // 用户身份确定后，标记为不再连接中 (连接将在另一个 useEffect 中进行)
    // setIsConnecting(false); // 移动到 connectWebSocket 中处理
    console.log(`User Identity: ${storedUserId} (${storedUserName})`);
  }, []);

  // --- 历史消息加载函数 ---
  const fetchHistory = useCallback(async (beforeTimestamp = null) => {
    if (isLoadingHistory || !hasMoreHistory) return; // 防止重复加载或没有更多历史

    setIsLoadingHistory(true);
    setError(null); // 清除旧错误
    const limit = 30; // 每次加载 30 条
    let url = `${BACKEND_API_URL}/api/messages?limit=${limit}`;
    if (beforeTimestamp) {
      url += `&before_timestamp=${encodeURIComponent(beforeTimestamp)}`;
    }
    console.log(`正在加载历史消息: ${url}`);

    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const historyMessages = await response.json();
      console.log(`收到 ${historyMessages.length} 条历史消息`);

      if (historyMessages.length > 0) {
        // 将历史消息添加到当前消息列表的 *开头*
        setMessages((prevMessages) => [...historyMessages, ...prevMessages]);
        // 更新最老消息的时间戳
        oldestMessageTimestamp.current = historyMessages[0].timestamp;
      }

      // 如果返回的消息数量小于请求的数量，说明没有更多历史了
      if (historyMessages.length < limit) {
        setHasMoreHistory(false);
        console.log("没有更多历史消息了。");
      }
    } catch (err) {
      console.error('加载历史消息失败:', err);
      setError('加载历史消息失败，请稍后重试。');
      // 可以考虑在这里设置 hasMoreHistory 为 false，防止无限重试
      // setHasMoreHistory(false);
    } finally {
      setIsLoadingHistory(false);
      if (!initialLoadComplete.current) {
          initialLoadComplete.current = true; // 标记首次加载完成
           // 首次加载完成后滚动到底部
           setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: "auto" }), 100); // 延迟确保渲染完成
      }
    }
  }, [isLoadingHistory, hasMoreHistory]); // 依赖加载状态和是否有更多

  // --- WebSocket 连接管理 ---
  const connectWebSocket = useCallback(() => {
    if (!userId || !userName || ws.current) {
        console.log("WebSocket 连接条件不满足或已存在连接。");
        return; // 确保有用户信息且没有现有连接
    }

    setIsConnecting(true); // 开始连接
    setError(null); // 清除旧错误
    console.log(`正在连接 WebSocket: ${BACKEND_WS_URL}/ws/${userId}/${userName}`);
    const socket = new WebSocket(`${BACKEND_WS_URL}/ws/${userId}/${userName}`);
    ws.current = socket; // 存储 WebSocket 实例

    socket.onopen = () => {
      console.log('WebSocket 连接成功');
      setIsConnected(true);
      setIsConnecting(false);
      setError(null);
      // --- 连接成功后，进行首次历史消息加载 ---
      initialLoadComplete.current = false; // 重置首次加载标记
      oldestMessageTimestamp.current = null; // 重置时间戳
      setHasMoreHistory(true); // 重置是否有更多历史
      setMessages([]); // 清空旧消息 (如果需要)
      fetchHistory(); // 首次加载
    };

    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        console.log('收到消息:', message);

        if (message.type === 'message') {
          setMessages((prevMessages) => [...prevMessages, message]);
          // 更新最老消息时间戳 (如果这是第一条消息)
          if (prevMessages.length === 0) {
              oldestMessageTimestamp.current = message.timestamp;
          }
        } else if (message.type === 'user_list_update') {
          setUsers(message.users);
        } else if (message.type === 'system') {
           // 可以将系统消息也加入 messages 列表，但需区分样式
           setMessages((prevMessages) => [...prevMessages, message]);
        } else {
            console.warn("收到未知类型的消息:", message);
        }
      } catch (err) {
        console.error('处理消息失败:', err);
        // 可以选择性地显示错误给用户
      }
    };

    socket.onerror = (event) => {
      console.error('WebSocket 错误:', event);
      setError('WebSocket 连接出错，请检查后端服务或网络连接。');
      setIsConnected(false);
      setIsConnecting(false); // 连接失败
      ws.current = null; // 清理引用
    };

    socket.onclose = (event) => {
      console.log('WebSocket 连接关闭:', event.code, event.reason);
      setIsConnected(false);
      setIsConnecting(false); // 连接已关闭
      ws.current = null; // 清理引用
      // 可选：尝试自动重连
      // setTimeout(connectWebSocket, 5000); // 5秒后尝试重连
      if (event.code !== 1000) { // 1000 是正常关闭
        setError('WebSocket 连接意外断开。');
      }
    };

  }, [userId, userName, fetchHistory]); // 添加 fetchHistory 依赖

  // 当 userId 和 userName 设置好后，开始连接 WebSocket
  useEffect(() => {
    if (userId && userName) {
        connectWebSocket();
    }

    // 组件卸载时关闭 WebSocket 连接
    return () => {
      if (ws.current && ws.current.readyState === WebSocket.OPEN) {
        console.log("组件卸载，关闭 WebSocket");
        ws.current.close(1000, "组件卸载"); // 正常关闭
      }
      ws.current = null; // 清理引用
    };
  }, [userId, userName]); // 只依赖用户身份


  // --- 消息发送 ---
  const sendMessage = useCallback(() => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN && inputValue.trim()) {
      const messageData = {
        type: 'message',
        content: inputValue,
        messageType: 'TEXT', // 明确是文本消息
      };
      ws.current.send(JSON.stringify(messageData));
      console.log('发送消息:', messageData);
      setInputValue(''); // 清空输入框
    } else {
        console.warn("无法发送消息：WebSocket 未连接或输入为空");
        if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
            setError("连接已断开，无法发送消息。请尝试刷新页面重连。");
        }
    }
  }, [inputValue]); // 依赖 inputValue

  // 处理回车键发送
  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) { // 按下 Enter 且没有按 Shift
      event.preventDefault(); // 阻止默认的换行行为
      sendMessage();
    }
  };

  // --- 图片上传与发送 ---
   const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      console.log("选择了文件:", file.name);
      uploadFile(file);
      // 清空文件输入框的值，以便用户可以再次选择同一个文件
      event.target.value = null;
    }
  };

  const uploadFile = async (file) => {
    if (!ws.current || ws.current.readyState !== WebSocket.OPEN) {
        setError("连接已断开，无法上传图片。");
        return;
    }
    if (!userId) {
        setError("用户信息丢失，无法上传图片。");
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    // 将 user_id 添加到 FormData 中
    formData.append('userId', userId);

    try {
        console.log(`上传图片到: ${BACKEND_API_URL}/api/upload`);
        const response = await fetch(`${BACKEND_API_URL}/api/upload`, {
            method: 'POST',
            body: formData,
        });

        const result = await response.json();

        if (response.ok && result.success && result.url) {
            console.log('图片上传成功:', result.url);
            // 构造图片消息发送给 WebSocket
            const imageUrlMessage = {
                type: 'message',
                content: result.url, // 后端返回的相对或绝对 URL
                messageType: 'IMAGE',
                // 可选：发送图片元数据，如宽度/高度，前端可以先获取
                // metadata: { width: ..., height: ... }
            };
            ws.current.send(JSON.stringify(imageUrlMessage));
            console.log('发送图片消息:', imageUrlMessage);
        } else {
            console.error('图片上传失败:', result.error || '未知错误');
            setError(`图片上传失败: ${result.error || '服务器内部错误'}`);
        }
    } catch (err) {
        console.error('上传文件 fetch 错误:', err);
        setError(`网络错误或服务器无响应: ${err.message}`);
    }
};

  // --- 切换身份 ---
  const changeIdentity = () => {
    console.log("正在切换身份...");
    // 1. 清除本地存储
    localStorage.removeItem('userId');
    localStorage.removeItem('userName');

    // 2. 关闭当前 WebSocket 连接 (如果存在且打开)
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.close(1000, "用户切换身份"); // 正常关闭
    }
     ws.current = null; // 清理引用

    // 3. 重置状态触发 useEffect 重新生成身份和连接
    setUserId(null);
    setUserName(null);
    setMessages([]);
    setUsers([]);
    setIsConnected(false);
    setIsConnecting(true); // 开始重新连接流程
    setError(null);
     // useEffect 会检测到 userId/userName 变化，然后生成新的并尝试重连
     // 强制页面刷新也是一种简单的方式：
     // window.location.reload();
  };

  // --- 自动滚动到消息列表底部 ---
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]); // 依赖消息列表

  // --- 滚动加载更多历史消息 ---
  useEffect(() => {
    const messageArea = messagesAreaRef.current;
    if (!messageArea) return;

    const handleScroll = () => {
        // 当滚动条距离顶部很近时 (例如小于 50px)，并且没有正在加载，并且还有更多历史
        if (messageArea.scrollTop < 50 && !isLoadingHistory && hasMoreHistory && initialLoadComplete.current) {
            console.log("滚动到顶部，加载更多历史...");
            // 使用当前最老消息的时间戳去获取更早的消息
            if (oldestMessageTimestamp.current) {
                fetchHistory(oldestMessageTimestamp.current);
            }
        }
    };

    messageArea.addEventListener('scroll', handleScroll);

    // 清理事件监听器
    return () => {
      messageArea.removeEventListener('scroll', handleScroll);
    };
  }, [isLoadingHistory, hasMoreHistory, fetchHistory]); // 依赖这些状态和函数

  // --- 自动滚动到底部 (只对新消息生效) ---
  useEffect(() => {
    // 只有在首次加载完成后，或者不是正在加载历史时才自动滚动到底部
    if (initialLoadComplete.current && !isLoadingHistory) {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
    // 注意：首次加载历史后，我们希望用户停留在历史消息的位置，而不是跳到底部
    // 因此，依赖项不应包含 messages，而是依赖一个标记或消息数量变化
    // 但简单的实现是只在非加载历史状态下滚动
  }, [messages.length, isLoadingHistory]); // 依赖消息数量和加载状态

  // --- UI 渲染 ---
  return (
    <div className="app-container">
      <header className="app-header">
        <h1>匿名聊天室 (React + FastAPI)</h1>
        <div className="status-bar">
          {isConnecting ? (
            <span className="status-connecting">正在连接...</span>
          ) : isConnected ? (
            <span className="status-connected">已连接</span>
          ) : (
            <span className="status-disconnected">已断开</span>
          )}
          {userId && userName && (
            <span className="user-info"> | 身份: {userName} ({userId})</span>
          )}
          {error && <span className="error-message"> | 错误: {error}</span>}
        </div>
      </header>

      <div className="main-content">
        {/* 用户列表 */}
        <aside className="user-list-panel">
          <h2>在线用户 ({users.length})</h2>
          <ul>
            {users.map((user) => (
              <li key={user.id} className={user.id === userId ? 'current-user' : ''}>
                {user.name} {user.id === userId ? '(你)' : ''}
              </li>
            ))}
          </ul>
           <button onClick={changeIdentity} className="change-identity-button">切换身份</button>
        </aside>

        {/* 聊天区域 */}
        <section className="chat-panel">
          <div className="messages-area" ref={messagesAreaRef}>
            {/* 添加加载指示器 */} 
            {isLoadingHistory && <div className="loading-history">正在加载历史消息...</div>}
            
            {messages.map((msg, index) => {
              // 判断是否是 AI Agent 发送的消息
              const isAgent = msg.sender?.id?.startsWith('agent_');
              // 判断消息来源，并组合 CSS 类名
              const messageClass = msg.type === 'system'
                ? 'system-message'
                : msg.sender?.id === userId
                  ? 'my-message'
                  : isAgent
                    ? 'other-message agent-message' // Agent 消息也视为 other，但添加 agent-message 类
                    : 'other-message';

              return (
                <div key={msg.timestamp || index} className={`message-item ${messageClass}`}>
                    {/* 对于非系统、非自己的消息，显示发送者名称 */}
                    {msg.type === 'message' && msg.sender?.id !== userId && (
                        <span className="message-sender">
                            {msg.sender.name}
                            {/* 如果是 Agent，可以在名字后加标识 */}
                            {/* {isAgent && ' (助手)'} */}
                        </span>
                    )}
                    {/* 渲染消息内容 */}
                    {msg.type === 'system' ? (
                        <span className="message-content system-content">{msg.content}</span>
                    ) : msg.messageType === 'TEXT' ? (
                        <span className="message-content">{msg.content}</span>
                    ) : msg.messageType === 'IMAGE' ? (
                        <img
                            src={msg.content.startsWith('/') ? `${BACKEND_API_URL}${msg.content}` : msg.content}
                            alt="聊天图片"
                            className="message-image"
                        />
                    ) : (
                        <span className="message-content">[未知消息类型]</span>
                    )}
                     {/* 显示时间戳 (可选) */}
                     {msg.timestamp && (
                       <span className="message-timestamp">
                         {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                       </span>
                     )}
                </div>
              );
            })}
            {/* 用于自动滚动的空元素 */}
            <div ref={messagesEndRef} />
          </div>

          <div className="input-area">
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown} // 添加回车键监听
              placeholder="输入消息... (Shift+Enter 换行)"
              rows="3"
              disabled={!isConnected} // 连接断开时禁用
            />
            <div className="input-buttons">
                <button onClick={() => fileInputRef.current?.click()} disabled={!isConnected}>
                    图片
                </button>
                {/* 隐藏的文件输入框 */}
                <input
                    type="file"
                    ref={fileInputRef}
                    style={{ display: 'none' }}
                    onChange={handleFileChange}
                    accept="image/*" // 只接受图片文件
                />
                <button onClick={sendMessage} disabled={!isConnected || !inputValue.trim()}>
                    发送
                </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

export default App;
