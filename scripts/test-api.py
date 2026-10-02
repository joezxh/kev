#!/usr/bin/env python3
"""
Kev-4B API 测试客户端
用于验证 Kev-4B 决策模型服务的可用性
"""

import httpx
import json
from typing import Optional


class KevAPIClient:
    """Kev-4B API 客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8008", model: str = "kev-latest"):
        self.base_url = base_url
        self.model = model
        self.client = httpx.AsyncClient(timeout=300.0)
    
    async def health_check(self) -> bool:
        """检查服务健康状态"""
        try:
            response = await self.client.get(f"{self.base_url}/v1/models")
            return response.status_code == 200
        except Exception as e:
            print(f"❌ 健康检查失败：{e}")
            return False
    
    async def get_models(self) -> dict:
        """获取可用模型列表"""
        response = await self.client.get(f"{self.base_url}/v1/models")
        response.raise_for_status()
        return response.json()
    
    async def system_one(self, state: str, questions: dict) -> dict:
        """
        发送系统决策请求
        
        Args:
            state: 上下文状态描述
            questions: 问题字典，包含 type/instructions/criteria
        
        Returns:
            API 响应结果
        """
        response = await self.client.post(
            f"{self.base_url}/v1/systemone",
            json={
                "state": state,
                "model": self.model,
                "questions": questions
            }
        )
        response.raise_for_status()
        return response.json()
    
    async def close(self):
        """关闭客户端连接"""
        await self.client.aclose()


async def main():
    """运行测试用例"""
    client = KevAPIClient()
    
    try:
        # 1. 健康检查
        print("=" * 60)
        print("🧪 Kev-4B API 测试")
        print("=" * 60)
        
        healthy = await client.health_check()
        if not healthy:
            print("❌ 服务未启动或无法连接")
            print("💡 请确保已运行：docker compose up -d")
            return
        
        print("✅ 服务已就绪")
        
        # 2. 获取模型信息
        print("\n📋 获取模型信息...")
        models = await client.get_models()
        print(json.dumps(models, indent=2, ensure_ascii=False))
        
        # 3. 测试场景 1：简单客服工单分类
        print("\n📝 测试场景 1：客服工单分类")
        questions_1 = {
            "team": {
                "type": "choice",
                "instructions": "哪个团队应该处理这个工单？",
                "criteria": {
                    "returns": "退换货、尺码不对、商品损坏",
                    "shipping": "物流延误、包裹丢失、配送问题",
                    "billing": "支付问题、发票、重复扣款"
                }
            },
            "urgent": {
                "type": "noul",
                "instructions": "是否需要紧急处理？",
                "criteria": {"true": None, "false": None}
            },
            "frustration": {
                "type": "score",
                "instructions": "客户有多沮丧？",
                "criteria": ["Calm", "Frustrated", "Very angry"]
            }
        }
        
        state_1 = "鞋子晚到了两周而且尺码不对，另外我的信用卡被 charges 了两次。"
        
        result_1 = await client.system_one(state_1, questions_1)
        print(json.dumps(result_1, indent=2, ensure_ascii=False))
        
        # 4. 测试场景 2：技术支持请求
        print("\n📝 测试场景 2：技术支持请求")
        questions_2 = {
            "category": {
                "type": "choice",
                "instructions": "这是什么类型的问题？",
                "criteria": {
                    "technical": "软件故障、错误提示、功能异常",
                    "account": "登录问题、密码重置、账户安全",
                    "billing": "订阅、付费、退款"
                }
            },
            "severity": {
                "type": "score",
                "instructions": "问题严重程度如何？",
                "criteria": ["Low impact", "Moderate issue", "Critical blocker"]
            }
        }
        
        state_2 = "我的订单显示已发货但已经三天没有更新了。追踪链接也无法访问。"
        
        result_2 = await client.system_one(state_2, questions_2)
        print(json.dumps(result_2, indent=2, ensure_ascii=False))
        
        # 5. 总结
        print("\n" + "=" * 60)
        print("✅ 所有测试完成！")
        print("=" * 60)
        
    except httpx.HTTPError as e:
        print(f"\n❌ API 调用失败：{e}")
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误：{e}")
    finally:
        await client.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
