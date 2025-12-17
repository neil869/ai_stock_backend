#!/usr/bin/env python3
"""
测试更新时间字段的功能
"""

import requests
import json
from datetime import datetime

def test_predict_detail():
    """测试预测详情功能，验证update_time字段"""
    print("测试预测详情功能...")
    
    # 直接测试历史预测API，获取最新的预测结果
    all_predictions = requests.post("http://localhost:8001/history-predict", json={"stock_code": "000001", "limit": 1})
    
    if all_predictions.status_code == 200:
        predictions_result = all_predictions.json()
        print(f"历史预测查询成功，响应: {predictions_result}")
        
        if 'predictions' in predictions_result and len(predictions_result['predictions']) > 0:
            # 获取第一个预测结果
            first_prediction = predictions_result['predictions'][0]
            print(f"预测结果: {first_prediction}")
            
            # 检查是否包含update_time字段
            if 'update_time' in first_prediction:
                print(f"✓ 成功: 预测结果包含update_time字段: {first_prediction['update_time']}")
                return True
            else:
                print("✗ 失败: 预测结果不包含update_time字段")
        else:
            print("✗ 失败: 没有返回预测结果")
    else:
        print(f"✗ 失败: 获取历史预测结果失败，状态码: {all_predictions.status_code}")
        print(f"错误信息: {all_predictions.text}")
    return False

def test_prediction():
    """测试预测功能"""
    print("\n测试预测功能...")
    
    # 调用预测API
    response = requests.get("http://localhost:8001/api/predict?code=000001")
    
    if response.status_code == 200:
        result = response.json()
        print(f"预测成功: {result['message']}")
        
        # 检查是否包含预测结果
        if 'data' in result:
            predict_data = result['data']
            print(f"预测结果: {predict_data}")
            
            # 获取预测结果的详细信息
            predict_id = predict_data['id']
            detail_response = requests.get(f"http://localhost:8001/api/predict/{predict_id}")
            
            if detail_response.status_code == 200:
                detail = detail_response.json()
                if 'data' in detail:
                    print(f"预测详情: {detail['data']}")
                    if 'update_time' in detail['data']:
                        print(f"✓ 成功: 包含update_time字段: {detail['data']['update_time']}")
                    else:
                        print("✗ 失败: 不包含update_time字段")
            else:
                print(f"✗ 失败: 获取预测详情失败，状态码: {detail_response.status_code}")
        else:
            print("✗ 失败: 没有返回预测结果")
    else:
        print(f"✗ 失败: 请求失败，状态码: {response.status_code}")
        print(f"错误信息: {response.text}")

if __name__ == "__main__":
    print("开始测试更新时间字段功能")
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)
    
    test_predict_detail()
    print("\n" + "="*50 + "\n")
    test_prediction()
    
    print("\n" + "="*50)
    print("测试完成")