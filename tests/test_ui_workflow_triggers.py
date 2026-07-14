import json

def test_workflow_triggers_sequence(auth_client, app):
    """
    Test the typical trigger flow from the UI:
    Pendiente -> En Proceso -> Entregado -> Facturacion -> Relacion de envio -> Enviado al cliente
    """
    # 1. Pendiente -> En Proceso
    response = auth_client.post(
        '/orders/10001/status',
        data=json.dumps({'status': 'En Proceso', 'notes': 'Actualizado desde UI'}),
        content_type='application/json',
    )
    assert response.status_code == 200
    assert response.get_json()['success'] is True
    
    # 2. En Proceso -> Entregado
    response = auth_client.post(
        '/orders/10001/status',
        data=json.dumps({'status': 'Entregado', 'notes': 'Actualizado desde UI'}),
        content_type='application/json',
    )
    assert response.status_code == 200
    assert response.get_json()['success'] is True

    # 3. Entregado -> Facturacion (Facturado in UI)
    response = auth_client.post(
        '/orders/10001/status',
        data=json.dumps({'status': 'Facturacion', 'notes': 'Actualizado desde UI'}),
        content_type='application/json',
    )
    assert response.status_code == 200
    assert response.get_json()['success'] is True
    
    # 4. Facturacion -> Relacion de envio (debe fallar si no hay factura)
    response = auth_client.post(
        '/orders/10001/status',
        data=json.dumps({'status': 'Relacion de envio', 'notes': 'Fallara sin factura'}),
        content_type='application/json',
    )
    assert response.status_code == 422

    # Agregamos factura al pedido temporalmente para poder avanzar
    with app.app_context():
        order = app.order_status_mgr.get_order('10001')
        order['factura_number'] = 'F-99999'
        app.order_status_mgr._save_database(force=True)

    # 4. Facturacion -> Relacion de envio (ahora debe pasar)
    response = auth_client.post(
        '/orders/10001/status',
        data=json.dumps({'status': 'Relacion de envio', 'notes': 'Actualizado desde UI con factura'}),
        content_type='application/json',
    )
    assert response.status_code == 200
    assert response.get_json()['success'] is True

    # 5. Relacion de envio -> Enviado al cliente
    response = auth_client.post(
        '/orders/10001/status',
        data=json.dumps({'status': 'Enviado al cliente', 'notes': 'Actualizado desde UI'}),
        content_type='application/json',
    )
    assert response.status_code == 200
    assert response.get_json()['success'] is True

    # Validate final state in the database
    with app.app_context():
        order = app.order_status_mgr.get_order('10001')
        assert order['status'] == 'Enviado al cliente'


def test_workflow_triggers_extra_statuses(auth_client, app):
    """
    Test the extra triggers from the UI: Cancelado and En Espera
    """
    # Pendiente -> En Espera
    response = auth_client.post(
        '/orders/10002/status',
        data=json.dumps({'status': 'En Espera', 'notes': 'Pausado desde UI'}),
        content_type='application/json',
    )
    assert response.status_code == 200
    assert response.get_json()['success'] is True

    # En Espera -> Cancelado
    response = auth_client.post(
        '/orders/10002/status',
        data=json.dumps({'status': 'Cancelado', 'notes': 'Cancelado desde UI'}),
        content_type='application/json',
    )
    assert response.status_code == 200
    assert response.get_json()['success'] is True

    # Validate final state
    with app.app_context():
        order = app.order_status_mgr.get_order('10002')
        assert order['status'] == 'Cancelado'
