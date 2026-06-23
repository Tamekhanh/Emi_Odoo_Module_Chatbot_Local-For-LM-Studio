/** @odoo-module **/
import { Component, useState, onWillStart, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class EmiChat extends Component {
    setup() {
        this.orm = useService("orm"); 
        this.chatBodyRef = useRef("chatBody");
        this.state = useState({
            messages: [],
            userInput: "",
        });

        onWillStart(async () => {
            try {
                // Không truyền userId nữa, Backend tự lo
                this.state.messages = await this.orm.call("emi.chat", "get_chat_history", []);
                this.scrollToBottom();
            } catch (error) {
                console.error("❌ Error loading chat history:", error);
            }
        });
    }

    async sendMessage() {
        if (!this.state.userInput.trim()) return;

        const userMsg = this.state.userInput;
        this.state.userInput = ""; 

        // Hiển thị tin nhắn user ngay lập tức
        this.state.messages.push({
            id: Date.now(),
            message: userMsg,
            is_user: true,
        });
        this.scrollToBottom();

        try {
            // Chỉ truyền 'message', không truyền 'userId'
            const response = await this.orm.call("emi.chat", "chat_with_emi", [userMsg]);

            this.state.messages.push({
                id: Date.now() + 1,
                message: response.response,
                is_user: false,
            });
        } catch (error) {
            console.error("❌ AI Error:", error);
            this.state.messages.push({
                id: Date.now() + 2,
                message: "Xin lỗi, Emi gặp sự cố kết nối. Vui lòng thử lại!",
                is_user: false,
            });
        }
        this.scrollToBottom();
    }

    onKeyDown(ev) {
        if (ev.key === "Enter") {
            this.sendMessage();
        }
    }

    scrollToBottom() {
        setTimeout(() => {
            const body = this.chatBodyRef.el;
            if (body) body.scrollTop = body.scrollHeight;
        }, 100);
    }

    async clearHistory() {
        // Xác nhận trước khi xóa để tránh bấm nhầm
        if (!confirm("Are you sure you want to delete all chat history? This action cannot be undone.")) {
            return;
        }

        try {
            // 1. Gọi backend để xóa trong database
            await this.orm.call("emi.chat", "clear_chat_history", []);
            
            // 2. Cập nhật state để xóa tin nhắn trên màn hình ngay lập tức
            this.state.messages = [];
            
            // Thông báo thành công (tùy chọn)
            console.log("✅ Chat history cleared successfully");
        } catch (error) {
            console.error("❌ Error clearing chat history:", error);
            alert("Failed to clear chat history. Please try again.");
        }
    }
}

EmiChat.template = "emi_ai_chatbot.EmiChat";
registry.category("actions").add("emi_chat_action", EmiChat);