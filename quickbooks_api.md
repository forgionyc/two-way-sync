# QuickBooks Invoicing API

The purpose of this document is to provide a reference for the QuickBooks Invoicing API. This API is used to create, read, update, and delete invoices in QuickBooks.

# Base URL

Content type:application/json
Production Base URL:https://quickbooks.api.intuit.com
Sandbox Base URL:https://sandbox-quickbooks.api.intuit.com

# API Endpoints

## Create Invoice

```
POST /v3/company/:companyId/invoice
```

```request
POST https://sandbox-quickbooks.api.intuit.com/v3/company/123456789/invoice

{
  "Line": [
    {
      "DetailType": "SalesItemLineDetail",
      "Amount": 100.0,
      "SalesItemLineDetail": {
        "ItemRef": {
          "name": "Services",
          "value": "1"
        }
      }
    }
  ],
  "CustomerRef": {
    "value": "1"
  }
}
```

```response
{
  "Invoice": {
    "TxnDate": "2015-07-24",
    "domain": "QBO",
    "PrintStatus": "NeedToPrint",
    "TotalAmt": 100.0,
    "Line": [
      {
        "LineNum": 1,
        "Amount": 100.0,
        "SalesItemLineDetail": {
          "TaxCodeRef": {
            "value": "NON"
          },
          "ItemRef": {
            "name": "Services",
            "value": "1"
          }
        },
        "Id": "1",
        "DetailType": "SalesItemLineDetail"
      },
      {
        "DetailType": "SubTotalLineDetail",
        "Amount": 100.0,
        "SubTotalLineDetail": {}
      }
    ],
    "DueDate": "2015-08-23",
    "ApplyTaxAfterDiscount": false,
    "DocNumber": "1069",
    "sparse": false,
    "ProjectRef": {
      "value": "39298034"
    },
    "Deposit": 0,
    "Balance": 100.0,
    "CustomerRef": {
      "name": "Amy's Bird Sanctuary",
      "value": "1"
    },
    "TxnTaxDetail": {
      "TotalTax": 0
    },
    "SyncToken": "0",
    "LinkedTxn": [],
    "ShipAddr": {
      "City": "Bayshore",
      "Line1": "4581 Finch St.",
      "PostalCode": "94326",
      "Lat": "INVALID",
      "Long": "INVALID",
      "CountrySubDivisionCode": "CA",
      "Id": "109"
    },
    "EmailStatus": "NotSet",
    "BillAddr": {
      "City": "Bayshore",
      "Line1": "4581 Finch St.",
      "PostalCode": "94326",
      "Lat": "INVALID",
      "Long": "INVALID",
      "CountrySubDivisionCode": "CA",
      "Id": "2"
    },
    "MetaData": {
      "CreateTime": "2015-07-24T10:33:39-07:00",
      "LastUpdatedTime": "2015-07-24T10:33:39-07:00"
    },
    "CustomField": [
      {
        "DefinitionId": "1",
        "Type": "StringType",
        "Name": "Crew #"
      }
    ],
    "Id": "238"
  },
  "time": "2015-07-24T10:33:39.11-07:00"
}
```

## Delete Invoice

```
POST /v3/company/<realmID>/invoice?operation=delete
```

```request
POST https://sandbox-quickbooks.api.intuit.com/v3/company/123456789/invoice?operation=delete

{
  "SyncToken": "3",
  "Id": "33"
}
```

```response
{
  "Invoice": {
    "status": "Deleted",
    "domain": "QBO",
    "Id": "33"
  },
  "time": "2013-03-15T00:18:15.322-07:00"
}
```

## Void Invoice

```
POST /v3/company/<realmID>/invoice?operation=void
```

```request
POST https://sandbox-quickbooks.api.intuit.com/v3/company/123456789/invoice?operation=void

{
  "SyncToken": "0",
  "Id": "129"
}
```

```response
{
  "Invoice": {
    "AllowOnlineACHPayment": false,
    "domain": "QBO",
    "TxnDate": "2014-11-09",
    "PrintStatus": "NEED_TO_PRINT",
    "SalesTermRef": {
      "value": "3"
    },
    "TotalAmt": 0,
    "Line": [
      {
        "Description": "Sod",
        "DetailType": "SALES_ITEM_LINE_DETAIL",
        "SalesItemLineDetail": {
          "TaxCodeRef": {
            "value": "TAX"
          },
          "Qty": 0,
          "ItemRef": {
            "name": "Sod",
            "value": "14"
          }
        },
        "LineNum": 1,
        "Amount": 0,
        "Id": "1"
      },
      {
        "Description": "2 cubic ft. bag",
        "DetailType": "SALES_ITEM_LINE_DETAIL",
        "SalesItemLineDetail": {
          "TaxCodeRef": {
            "value": "TAX"
          },
          "Qty": 0,
          "ItemRef": {
            "name": "Soil",
            "value": "15"
          }
        },
        "LineNum": 2,
        "Amount": 0,
        "Id": "2"
      },
      {
        "Description": "Weekly Gardening Service",
        "DetailType": "SALES_ITEM_LINE_DETAIL",
        "SalesItemLineDetail": {
          "TaxCodeRef": {
            "value": "NON"
          },
          "Qty": 0,
          "ItemRef": {
            "name": "Gardening",
            "value": "6"
          }
        },
        "LineNum": 3,
        "Amount": 0,
        "Id": "3"
      },
      {
        "Description": "Rock Fountain",
        "DetailType": "SALES_ITEM_LINE_DETAIL",
        "SalesItemLineDetail": {
          "TaxCodeRef": {
            "value": "TAX"
          },
          "Qty": 0,
          "ItemRef": {
            "name": "Rock Fountain",
            "value": "5"
          }
        },
        "LineNum": 4,
        "Amount": 0,
        "Id": "4"
      },
      {
        "Description": "Fountain Pump",
        "DetailType": "SALES_ITEM_LINE_DETAIL",
        "SalesItemLineDetail": {
          "TaxCodeRef": {
            "value": "TAX"
          },
          "Qty": 0,
          "ItemRef": {
            "name": "Pump",
            "value": "11"
          }
        },
        "LineNum": 5,
        "Amount": 0,
        "Id": "5"
      },
      {
        "DetailType": "SUB_TOTAL_LINE_DETAIL",
        "Amount": 0,
        "SubTotalLineDetail": {}
      }
    ],
    "DueDate": "2014-12-09",
    "MetaData": {
      "CreateTime": "2014-11-09T13:15:36-08:00",
      "LastUpdatedTime": "2016-03-16T12:27:10-07:00"
    },
    "DocNumber": "1036",
    "PrivateNote": "Voided",
    "sparse": false,
    "CustomerMemo": {
      "value": "Thank you for your business and have a great day!"
    },
    "ProjectRef": {
      "value": "39298045"
    },
    "Deposit": 0,
    "Balance": 0,
    "CustomerRef": {
      "name": "0969 Ocean View Road",
      "value": "8"
    },
    "TxnTaxDetail": {
      "TotalTax": 0
    },
    "AllowOnlineCreditCardPayment": false,
    "SyncToken": "1",
    "LinkedTxn": [],
    "BillEmail": {
      "Address": "Sporting_goods@intuit.com"
    },
    "ShipAddr": {
      "City": "Middlefield",
      "Line1": "370 Easy St.",
      "PostalCode": "94482",
      "Lat": "37.4031672",
      "Long": "-122.0642815",
      "CountrySubDivisionCode": "CA",
      "Id": "8"
    },
    "EmailStatus": "NOT_SET",
    "BillAddr": {
      "Line4": "Middlefield, CA  94482",
      "Line3": "370 Easy St.",
      "Line2": "Freeman Sporting Goods",
      "Line1": "Sasha Tillou",
      "Long": "INVALID",
      "Lat": "INVALID",
      "Id": "94"
    },
    "ApplyTaxAfterDiscount": false,
    "CustomField": [
      {
        "DefinitionId": "1",
        "StringValue": "105",
        "Type": "STRING_TYPE",
        "Name": "Crew #"
      }
    ],
    "Id": "129",
    "AllowOnlinePayment": false,
    "AllowIPNPayment": false
  },
  "time": "2016-03-16T12:27:10.711-07:00"
}
```

## Sparse update:

```
POST /v3/company/<realmID>/invoice
```


```request
POST https://sandbox-quickbooks.api.intuit.com/v3/company/123456789/invoice

{
  "SyncToken": "0",
  "Id": "238",
  "sparse": true,
  "DueDate": "2015-09-30"
}
```

```response
{
  "Invoice": {
    "TxnDate": "2015-07-24",
    "domain": "QBO",
    "PrintStatus": "NeedToPrint",
    "TotalAmt": 100.0,
    "Line": [
      {
        "LineNum": 1,
        "Amount": 100.0,
        "SalesItemLineDetail": {
          "TaxCodeRef": {
            "value": "NON"
          },
          "ItemRef": {
            "name": "Services",
            "value": "1"
          }
        },
        "Id": "1",
        "DetailType": "SalesItemLineDetail"
      },
      {
        "DetailType": "SubTotalLineDetail",
        "Amount": 100.0,
        "SubTotalLineDetail": {}
      }
    ],
    "DueDate": "2015-09-30",
    "ApplyTaxAfterDiscount": false,
    "DocNumber": "1069",
    "sparse": false,
    "ProjectRef": {
      "value": "39298045"
    },
    "Deposit": 0,
    "Balance": 100.0,
    "CustomerRef": {
      "name": "Amy's Bird Sanctuary",
      "value": "1"
    },
    "TxnTaxDetail": {
      "TotalTax": 0
    },
    "SyncToken": "1",
    "LinkedTxn": [],
    "ShipAddr": {
      "City": "Bayshore",
      "Line1": "4581 Finch St.",
      "PostalCode": "94326",
      "Lat": "INVALID",
      "Long": "INVALID",
      "CountrySubDivisionCode": "CA",
      "Id": "109"
    },
    "EmailStatus": "NotSet",
    "BillAddr": {
      "City": "Bayshore",
      "Line1": "4581 Finch St.",
      "PostalCode": "94326",
      "Lat": "INVALID",
      "Long": "INVALID",
      "CountrySubDivisionCode": "CA",
      "Id": "2"
    },
    "MetaData": {
      "CreateTime": "2015-07-24T10:33:39-07:00",
      "LastUpdatedTime": "2015-07-24T11:03:26-07:00"
    },
    "CustomField": [
      {
        "DefinitionId": "1",
        "Type": "StringType",
        "Name": "Crew #"
      }
    ],
    "Id": "238"
  },
  "time": "2015-07-24T11:03:26.674-07:00"
}
```

## Full Update:

```
POST /v3/company/<realmID>/invoice
```


```request
POST https://sandbox-quickbooks.api.intuit.com/v3/company/123456789/invoice

{
  "TxnDate": "2015-07-24",
  "domain": "QBO",
  "PrintStatus": "NeedToPrint",
  "TotalAmt": 150.0,
  "Line": [
    {
      "LineNum": 1,
      "Amount": 150.0,
      "SalesItemLineDetail": {
        "TaxCodeRef": {
          "value": "NON"
        },
        "ItemRef": {
          "name": "Services",
          "value": "1"
        }
      },
      "Id": "1",
      "DetailType": "SalesItemLineDetail"
    },
    {
      "DetailType": "SubTotalLineDetail",
      "Amount": 150.0,
      "SubTotalLineDetail": {}
    }
  ],
  "DueDate": "2015-08-23",
  "ApplyTaxAfterDiscount": false,
  "DocNumber": "1070",
  "sparse": false,
  "CustomerMemo": {
    "value": "Added customer memo."
  },
  "ProjectRef": {
    "value": "39298045"
  },
  "Balance": 150.0,
  "CustomerRef": {
    "name": "Amy's Bird Sanctuary",
    "value": "1"
  },
  "TxnTaxDetail": {
    "TotalTax": 0
  },
  "SyncToken": "0",
  "LinkedTxn": [],
  "ShipAddr": {
    "City": "Bayshore",
    "Line1": "4581 Finch St.",
    "PostalCode": "94326",
    "Lat": "INVALID",
    "Long": "INVALID",
    "CountrySubDivisionCode": "CA",
    "Id": "109"
  },
  "EmailStatus": "NotSet",
  "BillAddr": {
    "City": "Bayshore",
    "Line1": "4581 Finch St.",
    "PostalCode": "94326",
    "Lat": "INVALID",
    "Long": "INVALID",
    "CountrySubDivisionCode": "CA",
    "Id": "2"
  },
  "MetaData": {
    "CreateTime": "2015-07-24T10:35:08-07:00",
    "LastUpdatedTime": "2015-07-24T10:35:08-07:00"
  },
  "CustomField": [
    {
      "DefinitionId": "1",
      "Type": "StringType",
      "Name": "Crew #"
    }
  ],
  "Id": "239"
}
```

```response
{
  "Invoice": {
    "TxnDate": "2015-07-24",
    "domain": "QBO",
    "PrintStatus": "NeedToPrint",
    "TotalAmt": 150.0,
    "Line": [
      {
        "LineNum": 1,
        "Amount": 150.0,
        "SalesItemLineDetail": {
          "TaxCodeRef": {
            "value": "NON"
          },
          "ItemRef": {
            "name": "Services",
            "value": "1"
          }
        },
        "Id": "1",
        "DetailType": "SalesItemLineDetail"
      },
      {
        "DetailType": "SubTotalLineDetail",
        "Amount": 150.0,
        "SubTotalLineDetail": {}
      }
    ],
    "DueDate": "2015-08-23",
    "ApplyTaxAfterDiscount": false,
    "DocNumber": "1070",
    "sparse": false,
    "CustomerMemo": {
      "value": "Added customer memo."
    },
    "ProjectRef": {
      "value": "39298045"
    },
    "Deposit": 0,
    "Balance": 150.0,
    "CustomerRef": {
      "name": "Amy's Bird Sanctuary",
      "value": "1"
    },
    "TxnTaxDetail": {
      "TotalTax": 0
    },
    "SyncToken": "1",
    "LinkedTxn": [],
    "ShipAddr": {
      "CountrySubDivisionCode": "CA",
      "City": "Bayshore",
      "PostalCode": "94326",
      "Id": "118",
      "Line1": "4581 Finch St."
    },
    "EmailStatus": "NotSet",
    "BillAddr": {
      "CountrySubDivisionCode": "CA",
      "City": "Bayshore",
      "PostalCode": "94326",
      "Id": "117",
      "Line1": "4581 Finch St."
    },
    "MetaData": {
      "CreateTime": "2015-07-24T10:35:08-07:00",
      "LastUpdatedTime": "2015-07-24T10:53:39-07:00"
    },
    "CustomField": [
      {
        "DefinitionId": "1",
        "Type": "StringType",
        "Name": "Crew #"
      }
    ],
    "Id": "239"
  },
  "time": "2015-07-24T10:53:39.287-07:00"
}
```

## Query an invoice

```
GET /v3/company/<realmID>/query?query=<selectStatement>
```

```sql
select * from Invoice where id = '239'
```

```response
{
  "QueryResponse": {
    "startPosition": 1,
    "totalCount": 1,
    "maxResults": 1,
    "Invoice": [
      {
        "TxnDate": "2015-07-24",
        "domain": "QBO",
        "PrintStatus": "NeedToPrint",
        "TotalAmt": 150.0,
        "Line": [
          {
            "LineNum": 1,
            "Amount": 150.0,
            "SalesItemLineDetail": {
              "TaxCodeRef": {
                "value": "NON"
              },
              "ItemRef": {
                "name": "Services",
                "value": "1"
              }
            },
            "Id": "1",
            "DetailType": "SalesItemLineDetail"
          },
          {
            "DetailType": "SubTotalLineDetail",
            "Amount": 150.0,
            "SubTotalLineDetail": {}
          }
        ],
        "DueDate": "2015-08-23",
        "ApplyTaxAfterDiscount": false,
        "DocNumber": "1070",
        "sparse": false,
        "ProjectRef": {
          "value": "39298034"
        },
        "Deposit": 0,
        "Balance": 150.0,
        "CustomerRef": {
          "name": "Amy's Bird Sanctuary",
          "value": "1"
        },
        "TxnTaxDetail": {
          "TotalTax": 0
        },
        "SyncToken": "0",
        "LinkedTxn": [],
        "ShipAddr": {
          "City": "Bayshore",
          "Line1": "4581 Finch St.",
          "PostalCode": "94326",
          "Lat": "INVALID",
          "Long": "INVALID",
          "CountrySubDivisionCode": "CA",
          "Id": "109"
        },
        "EmailStatus": "NotSet",
        "BillAddr": {
          "City": "Bayshore",
          "Line1": "4581 Finch St.",
          "PostalCode": "94326",
          "Lat": "INVALID",
          "Long": "INVALID",
          "CountrySubDivisionCode": "CA",
          "Id": "2"
        },
        "MetaData": {
          "CreateTime": "2015-07-24T10:35:08-07:00",
          "LastUpdatedTime": "2015-07-24T10:35:08-07:00"
        },
        "CustomField": [
          {
            "DefinitionId": "1",
            "Type": "StringType",
            "Name": "Crew #"
          }
        ],
        "Id": "239"
      }
    ]
  },
  "time": "2015-07-24T10:38:50.01-07:00"
}
```

## Read an invoice

```
GET /v3/company/<realmID>/invoice/<invoiceId>
```

```response
{
  "Invoice": {
    "TxnDate": "2014-09-19",
    "domain": "QBO",
    "PrintStatus": "NeedToPrint",
    "SalesTermRef": {
      "value": "3"
    },
    "TotalAmt": 362.07,
    "Line": [
      {
        "Description": "Rock Fountain",
        "DetailType": "SalesItemLineDetail",
        "SalesItemLineDetail": {
          "TaxCodeRef": {
            "value": "TAX"
          },
          "Qty": 1,
          "UnitPrice": 275,
          "ItemRef": {
            "name": "Rock Fountain",
            "value": "5"
          }
        },
        "LineNum": 1,
        "Amount": 275.0,
        "Id": "1"
      },
      {
        "Description": "Fountain Pump",
        "DetailType": "SalesItemLineDetail",
        "SalesItemLineDetail": {
          "TaxCodeRef": {
            "value": "TAX"
          },
          "Qty": 1,
          "UnitPrice": 12.75,
          "ItemRef": {
            "name": "Pump",
            "value": "11"
          }
        },
        "LineNum": 2,
        "Amount": 12.75,
        "Id": "2"
      },
      {
        "Description": "Concrete for fountain installation",
        "DetailType": "SalesItemLineDetail",
        "SalesItemLineDetail": {
          "TaxCodeRef": {
            "value": "TAX"
          },
          "Qty": 5,
          "UnitPrice": 9.5,
          "ItemRef": {
            "name": "Concrete",
            "value": "3"
          }
        },
        "LineNum": 3,
        "Amount": 47.5,
        "Id": "3"
      },
      {
        "DetailType": "SubTotalLineDetail",
        "Amount": 335.25,
        "SubTotalLineDetail": {}
      }
    ],
    "DueDate": "2014-10-19",
    "ApplyTaxAfterDiscount": false,
    "DocNumber": "1037",
    "sparse": false,
    "CustomerMemo": {
      "value": "Thank you for your business and have a great day!"
    },
    "ProjectRef": {
      "value": "39298045"
    },
    "Deposit": 0,
    "Balance": 362.07,
    "CustomerRef": {
      "name": "Sonnenschein Family Store",
      "value": "24"
    },
    "TxnTaxDetail": {
      "TxnTaxCodeRef": {
        "value": "2"
      },
      "TotalTax": 26.82,
      "TaxLine": [
        {
          "DetailType": "TaxLineDetail",
          "Amount": 26.82,
          "TaxLineDetail": {
            "NetAmountTaxable": 335.25,
            "TaxPercent": 8,
            "TaxRateRef": {
              "value": "3"
            },
            "PercentBased": true
          }
        }
      ]
    },
    "SyncToken": "0",
    "LinkedTxn": [
      {
        "TxnId": "100",
        "TxnType": "Estimate"
      }
    ],
    "BillEmail": {
      "Address": "Familiystore@intuit.com"
    },
    "ShipAddr": {
      "City": "Middlefield",
      "Line1": "5647 Cypress Hill Ave.",
      "PostalCode": "94303",
      "Lat": "37.4238562",
      "Long": "-122.1141681",
      "CountrySubDivisionCode": "CA",
      "Id": "25"
    },
    "EmailStatus": "NotSet",
    "BillAddr": {
      "Line4": "Middlefield, CA  94303",
      "Line3": "5647 Cypress Hill Ave.",
      "Line2": "Sonnenschein Family Store",
      "Line1": "Russ Sonnenschein",
      "Long": "-122.1141681",
      "Lat": "37.4238562",
      "Id": "95"
    },
    "MetaData": {
      "CreateTime": "2014-09-19T13:16:17-07:00",
      "LastUpdatedTime": "2014-09-19T13:16:17-07:00"
    },
    "CustomField": [
      {
        "DefinitionId": "1",
        "StringValue": "102",
        "Type": "StringType",
        "Name": "Crew #"
      }
    ],
    "Id": "130"
  },
  "time": "2015-07-24T10:48:27.082-07:00"
}
```

# Webhooks
## Triggers:

| Operation / State | Event Description |
| :--- | :--- |
| `Void` | QBO Invoice has been voided |
| `Delete` | QBO Invoice has been deleted |
| `Update` | QBO Invoice has been updated |
| `Create` | QBO Invoice has been created |
| `Emailed` | QBO Invoice has been emailed |

## Sample payload:
New payload with CloudEvents format for 2026:
```json
[
  {
    "specversion": "1.0",
    "id": "88cd52aa-33b6-4351-9aa4-47572edbd068",
    "source": "intuit.dsnBgbseACLLRZNxo2dfc4evmEJdxde58xeeYcZliOU=",
    "type": "qbo.invoice.created.v1",
    "datacontenttype": "application/json",
    "time": "2025-09-10T21:31:25.179851517Z",
    "intuitentityid": "1234", // Maps to InvoiceId
    "intuitaccountid": "310687", // Maps to CompanyId equals to RealmId in quickbooks.
    "data": {}
  }
]
```