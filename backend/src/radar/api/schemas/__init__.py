"""Schemas (Pydantic) da API: o formato de entrada (query) e de saída (JSON).

São separados dos read models dos ports de propósito: o contrato HTTP pode mudar
(renomear um campo, somar um rótulo) sem mexer nas consultas, e vice-versa.
"""
